async function initKpiPage(){
  if(kpiLoaded)return;
  kpiLoaded=true;
  try{
    const[log,kpiLog]=await Promise.all([loadSimLog(),loadKpiLog().catch(()=>null)]);
    renderKpiPage(log);
    if(kpiLog)renderTeamKpiSection(kpiLog);
    else document.getElementById('team-kpi-table').innerHTML='<div style="padding:20px;color:#8b949e;text-align:center">KPIデータなし（初回実行後に表示されます）</div>';
  }catch(e){
    document.getElementById("kpi-hist-body").innerHTML='<tr><td colspan="9" style="text-align:center;color:#f85149;padding:20px">読み込み失敗: '+e.message+'</td></tr>';
  }
}
function renderKpiPage(log){
  const actives=getSimActives(log);
  const history=getSimHistory(log);
  const completed=history.filter(h=>h.result);
  const wins=completed.filter(h=>(h.result_pct||0)>0);
  const losses=completed.filter(h=>(h.result_pct||0)<=0);
  const winRate=completed.length?wins.length/completed.length*100:null;
  const avgWin=wins.length?wins.reduce((s,h)=>s+(h.result_pct||0),0)/wins.length:null;
  const avgLoss=losses.length?losses.reduce((s,h)=>s+(h.result_pct||0),0)/losses.length:null;
  // 仮説的中率: v2(daily_log.prev_match) + 旧(hypothesis_history.match) を両対応
  const allDlog=[...actives,...history].flatMap(a=>a.daily_log||[]);
  const dlogMatches=allDlog.filter(d=>d.prev_match===true||d.prev_match===false);
  const allHyp=[...actives,...history].flatMap(a=>a.hypothesis_history||[]);
  const hypRate=dlogMatches.length>0
    ?dlogMatches.filter(d=>d.prev_match===true).length/dlogMatches.length*100
    :(allHyp.length?allHyp.filter(h=>h.match).length/allHyp.length*100:null);
  const fmt=(v,good,pfx='',sfx='%')=>v===null?'-':`<span style="color:${v>=good?'#3fb950':'#f85149'}">${pfx}${v.toFixed(1)}${sfx}</span>`;
  document.getElementById('kpi-total').textContent=completed.length+'件';
  document.getElementById('kpi-winrate').innerHTML=fmt(winRate,50);
  document.getElementById('kpi-hyprate').innerHTML=fmt(hypRate,55);
  document.getElementById('kpi-avgwin').innerHTML=avgWin!==null?`<span style="color:#3fb950">+${avgWin.toFixed(1)}%</span>`:'-';
  document.getElementById('kpi-avgloss').innerHTML=avgLoss!==null?`<span style="color:${avgLoss>=-8?'#3fb950':'#f85149'}">${avgLoss.toFixed(1)}%</span>`:'-';
  document.getElementById('kpi-updated').textContent='更新: '+(log.last_updated||'-');
  const resultLabel={stopped_out:'損切り',target1_hit:'目標①',time_expired:'期間終了'};
  const resultCls={stopped_out:'loss',target1_hit:'win',time_expired:'time'};
  document.getElementById('kpi-hist-count').textContent=completed.length+'件';
  const tbody=document.getElementById('kpi-hist-body');
  if(completed.length===0){tbody.innerHTML='<tr><td colspan="9" style="text-align:center;color:#8b949e;padding:20px">履歴なし</td></tr>';return;}
  tbody.innerHTML=completed.map(h=>{
    const pct=h.result_pct||0;const cls=pct>0?'pos':pct<0?'neg':'neu';const res=h.result||'-';
    const hh=h.hypothesis_history||[];const hRate=hh.length?Math.round(hh.filter(x=>x.match).length/hh.length*100):null;
    return `<tr><td class="name">${h.name||'-'}</td><td class="code">${h.code||'-'}</td><td class="r">${(h.entry_price||0).toLocaleString()}</td><td class="r">${(h.current_price||h.entry_price||0).toLocaleString()}</td><td class="r ${cls}" style="font-family:monospace">${pct>=0?'+':''}${pct.toFixed(1)}%</td><td><span class="sim-result-badge ${resultCls[res]||''}">${resultLabel[res]||res}</span></td><td style="color:${hRate===null?'#8b949e':hRate>=55?'#3fb950':'#f85149'}">${hRate===null?'-':hRate+'%'}</td><td style="color:#8b949e">${h.days_elapsed||0}日</td><td style="color:#8b949e">${h.start_date||'-'}</td></tr>`;
  }).join('');
}
var lwChart=null,candleSeries=null,volumeSeries=null,sma50Series=null,sma150Series=null,sma200Series=null;
