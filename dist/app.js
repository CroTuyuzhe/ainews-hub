'use strict';
const $ = id => document.getElementById(id);
const number = v => typeof v === 'number' && Number.isFinite(v);
const fmt = (v, digits=2) => number(v) ? v.toLocaleString('zh-CN',{maximumFractionDigits:digits}) : '--';
const pct = v => number(v) ? `${v>0?'+':''}${fmt(v)}%` : '--';
const put = (id, value) => { $(id).textContent = value; };
let snapshot, range=7, market='a-share', charts=[], chartReady=false, chartLoading=false;
function element(tag, text, cls) { const e=document.createElement(tag); e.textContent=text; if(cls)e.className=cls; return e; }
function meta(metric, target) {
  const host=$(target); host.replaceChildren();
  const m=metric?.meta || {}, age=m.trade_date ? Math.floor((Date.now()-Date.parse(m.trade_date+'T00:00:00Z'))/86400000):null;
  const status=m.status==='fresh' && age>4 ? 'cached' : m.status;
  host.append(element('span',({fresh:'已采集',cached:'历史 / 缓存',missing:'暂无数据',demo:'演示数据'})[status]||'暂无数据','metric-badge '+status));
  host.append(element('span',`行情 ${m.trade_date||'未取得'} · ${m.source||'来源未提供'}`));
  if(m.fetched_at) host.append(element('span',` · 采集 ${new Date(m.fetched_at).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false})}`));
  if(m.reason)host.append(element('span',m.reason,'metric-reason'));
}
function selectMarket(next, focus=false) {
 market=next;
 for(const name of ['a-share','us-market']) { const active=name===next, tab=$('tab-'+name); tab.setAttribute('aria-selected',String(active)); tab.tabIndex=active?0:-1; tab.classList.toggle('active',active); $('panel-'+name).hidden=!active; if(active&&focus)tab.focus(); }
 document.querySelector('.score-explanation').hidden=next!=='a-share';
 requestAnimationFrame(()=>charts.forEach(c=>c.resize()));
}
for(const name of ['a-share','us-market']) {
 const tab=$('tab-'+name); tab.addEventListener('click',()=>selectMarket(name));
 tab.addEventListener('keydown',e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault(); selectMarket(e.key==='Home'?'a-share':e.key==='End'?'us-market':market==='a-share'?'us-market':'a-share',true);}});
}
document.querySelectorAll('[data-range]').forEach(b=>b.addEventListener('click',()=>{range=Number(b.dataset.range); document.querySelectorAll('[data-range]').forEach(x=>x.setAttribute('aria-pressed',String(Number(x.dataset.range)===range))); renderHistory();}));
function dates(metrics) { const days=[...new Set(metrics.map(m=>m?.meta?.trade_date).filter(Boolean))].sort(); return days.length ? `行情日期 ${days.join(' / ')}${days.length>1?' · 各指标日期不同，请分别查看':''}`:'尚无可验证行情'; }
function render(data) {
 snapshot=data; const a=data.a_share,u=data.us_market;
 $('loading').style.display='none'; $('error').style.display='none'; $('content').style.display='block';
 put('updateTimeText',`快照采集：${data.update_time||'尚未采集'}`); put('navTimeText','日度快照'); put('dataNote',data.data_note||'独立采集各项指标；缺失数据不计为零。');
 const metrics=[...a.indexes,a.market_sentiment,a.panic_index,a.volume,a.north_flow,u.vix,u.sp500];
 put('qualitySummary',`共 ${metrics.length} 项：${metrics.filter(m=>m.meta.status==='fresh').length} 项已采集 · ${metrics.filter(m=>m.meta.status==='cached').length} 项缓存 · ${metrics.filter(m=>m.meta.status==='missing').length} 项缺失。已采集不代表实时，行情日期见各卡片。`);
 put('aMarketDate',dates(metrics.slice(0,7))); put('usMarketDate',dates([u.vix,u.sp500]));
 $('indexGrid').replaceChildren(); a.indexes.forEach(m=>{const row=element('div','','index-item'); row.append(element('div',m.name,'idx-name'),element('div',fmt(m.value),'idx-price'),element('div',pct(m.change_pct),'idx-change '+(m.change_pct>=0?'up':'down'))); row.append(element('small',`行情 ${m.meta.trade_date||'未取得'} · ${m.meta.status==='cached'?'缓存':m.meta.status==='missing'?'缺失':'已采集'}`)); $('indexGrid').append(row);});
 meta(a.indexes[0],'meta-indexes');
 for(const k of ['market_sentiment','panic_index','volume','north_flow'])meta(a[k],'meta-'+k);
 for(const k of ['vix','sp500'])meta(u[k],'meta-'+k);
 $('sentimentGrid').replaceChildren(); for(const [k,label] of [['up_count','上涨'],['down_count','下跌'],['limit_up','涨停'],['limit_down','跌停']])$('sentimentGrid').append(element('div',`${label} ${fmt(a.market_sentiment[k],0)}`));
 put('panicValue',fmt(a.panic_index.value,1)); put('panicLabel',a.panic_index.label||'数据不足'); $('panicArc').style.strokeDashoffset=String(100.53*(1-(number(a.panic_index.value)?a.panic_index.value:0)/100));
 put('northFlowValue',number(a.north_flow.value)?`${fmt(a.north_flow.value)} 亿`:'--'); put('volumeValue',number(a.volume.value)?`${fmt(a.volume.value)} 亿`:'--'); put('volumeVsAvg',pct(a.volume.vs_20day_avg));
 for(const k of ['vix','sp500']){put(k+'Value',fmt(u[k].value));put(k+'Change',pct(u[k].change_pct));}
 const components=$('scoreComponents'); components.replaceChildren();
 if(!a.panic_index.components?.length)components.append(element('p','输入数据不足，暂不合成分数。'));
 else {const table=element('table','','history-table');table.append(element('caption','本期分项贡献'));const body=document.createElement('tbody');for(const c of a.panic_index.components){const row=document.createElement('tr');row.append(element('td',c.name),element('td',`${fmt(c.score)} × ${c.weight*100}%`),element('td',fmt(c.contribution)));body.append(row);}table.append(body);components.append(table);}
 renderHistory(); selectMarket(market);
}
function renderHistory(){
 if(!snapshot)return; charts.forEach(c=>c.destroy());charts=[];
 for(const [id,m] of [['panicChart',snapshot.a_share.panic_index],['northFlowChart',snapshot.a_share.north_flow],['volumeChart',snapshot.a_share.volume],['vixChart',snapshot.us_market.vix],['sp500Chart',snapshot.us_market.sp500]]){
  const canvas=$(id),box=canvas.parentElement; box.parentElement.querySelectorAll(`[data-history="${id}"]`).forEach(n=>n.remove());
  const points=m.history.slice(-range),hint=element('p',`请求 ${range} 个交易日 · 现有 ${points.length} 条记录${points.length<range?'，不补造缺失日期':''}`,'chart-hint');hint.dataset.history=id;
  const details=element('details','','chart-table');details.dataset.history=id;details.append(element('summary',`查看历史数据（${points.length} 条）`));
  const wrap=element('div','','history-table-wrap'),table=element('table');table.append(element('caption','行情日期 / 数值'));const body=document.createElement('tbody');
  points.slice().reverse().forEach(p=>{const tr=document.createElement('tr');tr.append(element('td',p.date),element('td',fmt(p.value)));body.append(tr);});table.append(body);wrap.append(table);details.append(wrap);box.after(hint,details);
  canvas.hidden=!chartReady||points.length<2; box.hidden=canvas.hidden;
  if(chartReady&&points.length>=2){try{charts.push(new Chart(canvas,{type:'line',data:{labels:points.map(p=>p.date),datasets:[{data:points.map(p=>p.value),borderColor:'#33ff77',borderWidth:2,pointRadius:0,tension:.15}]},options:{responsive:true,maintainAspectRatio:false,animation:false,plugins:{legend:{display:false}},scales:{x:{display:false},y:{display:false}}}}));}catch{hint.textContent+=' · 图表不可用，请查看表格';}}
 }
}
async function refresh(){
 $('refreshData').disabled=true;
 try{const response=await fetch('./data.json',{cache:'no-store',signal:AbortSignal.timeout(12000)});if(!response.ok)throw Error(`HTTP ${response.status}`);const data=await response.json();if(data.schema_version!==2||!Array.isArray(data.a_share?.indexes)||!data.us_market)throw Error('快照格式不兼容');render(data);}
 catch(e){if(snapshot){put('qualitySummary','重新加载失败，已保留上次快照。请稍后重试。');}else{$('loading').style.display='none';$('error').style.display='block';put('errorMsg','快照加载失败，请检查网络后重试。');}}
 finally{$('refreshData').disabled=false;}
}
function loadCharts(){
 if(chartLoading||chartReady)return;chartLoading=true;put('chartService','正在加载图表组件；数值和表格可独立查看。');
 const script=document.createElement('script');script.src='https://cdn.jsdelivr.net/npm/chart.js@4.4.8/dist/chart.umd.min.js';let settled=false;
 const finish=ok=>{if(settled)return;settled=true;clearTimeout(timer);chartLoading=false;chartReady=ok;const host=$('chartService');host.replaceChildren(element('span',ok?'图表组件已就绪':'图表组件加载失败，数值与历史表格仍可使用。'));if(!ok){script.remove();const b=element('button','重试图表');b.onclick=loadCharts;host.append(b);}renderHistory();};
 const timer=setTimeout(()=>finish(false),10000);script.onload=()=>finish(typeof Chart!=='undefined');script.onerror=()=>finish(false);document.head.append(script);
}
$('refreshData').onclick=refresh;
window.loadData=refresh;
refresh();loadCharts();
