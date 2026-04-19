async function initSimPage(){
  if(simLoaded)return;
  simLoaded=true;
  try{
    const log=await loadSimLog();
    renderSimPage(log);
  }catch(e){
    document.getElementById("sim-cards-wrap").innerHTML='<div class="sim-empty">読み込み失敗: '+e.message+'</div>';
  }
}
let kpiLoaded=false;
function normalizeSim(s){
  // 旧フォーマットのフィールド名を新フォーマットに統一
  return {
    code: s.code||s.stock_code||'',
    name: s.name||s.stock_name||s.company_name||'-',
    entry_price: s.entry_price||s.entry_target||s.purchase_price||0,
    stop_loss: s.stop_loss||s.stop_target||0,
    target1: s.target1||s.target_price||s.profit_target||0,
    current_price: s.current_price||s.entry_price||s.entry_target||0,
    current_pct: s.current_pct||0,
    days_elapsed: s.days_elapsed||s.holding_days||0,
    rs_26w: s.rs_26w||s.rs26w||0,
    next_hypothesis: s.next_hypothesis||null,
    result: s.result||s.actual_result||null,
    result_pct: s.result_pct||null,
    start_date: s.start_date||s.entry_date||''
  };
}
function getSimHistory(log){
  const raw=log.history||(log.simulations?log.simulations.filter(s=>s.result||s.actual_result):[])||[];
  return raw.map(normalizeSim).slice().reverse();
}
function getSimActives(log){
  const raw=log.actives||(log.simulations?log.simulations.filter(s=>!s.result&&!s.actual_result):null)||(log.active?[log.active]:[]);
  return (raw||[]).map(normalizeSim);
}
function renderSimPage(log){
  const actives=getSimActives(log);
  const history=getSimHistory(log);
  document.getElementById("sim-count").textContent=actives.length+"件追跡中";
  const wrap=document.getElementById("sim-cards-wrap");
  const dirIcon={'上昇':'▲','下落':'▼','横ばい':'━'};
  const dirColor={'上昇':'#3fb950','下落':'#f85149','横ばい':'#8b949e'};
  const confColor={'高':'#3fb950','中':'#f0b429','低':'#8b949e'};
  const resultLabel={stopped_out:'損切り',target1_hit:'目標①',time_expired:'期間終了'};
  const resultCls={stopped_out:'loss',target1_hit:'win',time_expired:'time'};
  if(actives.length===0){wrap.innerHTML='<div class="sim-empty">現在追跡中の銘柄はありません</div>';}
  else{
    wrap.innerHTML=actives.map(a=>{
      const pct=a.current_pct||0;
      const pctCls=pct>0?'pos':pct<0?'neg':'neu';
      const ep=a.entry_price||0;
      const sl=a.stop_loss||0;
      const t1=a.target1||0;
      const maxDays=a.scenarios?20:10;
      const prog=Math.min(100,((a.days_elapsed||0)/maxDays)*100);
      // ① 対象銘柄
      const s1=`<div style="margin-bottom:10px">
        <div style="font-size:10px;color:#f0b429;font-weight:600;margin-bottom:6px;text-transform:uppercase;letter-spacing:.6px">① 対象銘柄 <span style="color:#8b949e;font-weight:400;font-size:10px">銘柄選定・仮説チーム</span></div>
        <div style="display:flex;justify-content:space-between;align-items:flex-start">
          <div><div style="font-size:15px;font-weight:700;color:#e6edf3">${a.name||'-'}</div><div style="font-size:11px;color:#8b949e;font-family:monospace">${a.code||'-'} / RS26w ${(a.rs_26w||0).toFixed(2)}</div></div>
          <div class="sim-pct ${pctCls}" style="font-size:20px">${pct>=0?'+':''}${pct.toFixed(2)}%</div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin-top:8px">
          <div style="background:#0d1117;border-radius:6px;padding:6px 8px"><div style="font-size:10px;color:#8b949e">エントリー</div><div style="font-size:13px;font-family:monospace">${ep.toLocaleString()}円</div></div>
          <div style="background:#0d1117;border-radius:6px;padding:6px 8px"><div style="font-size:10px;color:#8b949e">現在値</div><div style="font-size:13px;font-family:monospace">${(a.current_price||0).toLocaleString()}円</div></div>
          <div style="background:#0d1117;border-radius:6px;padding:6px 8px"><div style="font-size:10px;color:#8b949e">経過</div><div style="font-size:13px">${a.days_elapsed||0}/${maxDays}日</div></div>
          <div style="background:#0d1117;border-radius:6px;padding:6px 8px"><div style="font-size:10px;color:#f85149">損切り</div><div style="font-size:13px;font-family:monospace;color:#f85149">${sl.toLocaleString()}円</div></div>
          <div style="background:#0d1117;border-radius:6px;padding:6px 8px"><div style="font-size:10px;color:#3fb950">目標①</div><div style="font-size:13px;font-family:monospace;color:#3fb950">${t1.toLocaleString()}円</div></div>
          <div style="background:#0d1117;border-radius:6px;padding:6px 8px"><div style="font-size:10px;color:#8b949e">開始日</div><div style="font-size:12px">${a.start_date||'-'}</div></div>
        </div>
        <div class="sim-progress" style="margin-top:8px"><div class="sim-progress-bar" style="width:${prog}%"></div></div>
      </div>`;
      // ② 3シナリオ (v2) または 旧フォーマット
      const scens=a.scenarios;
      const curHyp=a.current_hypothesis||{};
      const leadSid=curHyp.leading_scenario||null;
      const scenConf={'bull':'#3fb950','base':'#f0b429','bear':'#f85149'};
      const scenLabel={'bull':'📈 強気','base':'➡ 中立','bear':'📉 弱気'};
      let s2='';
      if(scens){
        const week=Math.min(4,Math.floor((a.days_elapsed||0)/5)+1);
        const wKey=`w${week}_pct`;
        const scenTiles=['bull','base','bear'].map(sid=>{
          const sc=scens[sid]||{};
          const prob=sc.probability||33;
          const wTarget=sc[wKey]||sc.w1_pct||0;
          const isLead=sid===leadSid;
          const borderColor=isLead?scenConf[sid]:'#30363d';
          const bgColor=isLead?'rgba(48,54,61,0.6)':'#0d1117';
          return `<div style="padding:8px;background:${bgColor};border-radius:8px;border:1px solid ${borderColor};${isLead?'box-shadow:0 0 6px '+scenConf[sid]+'44':''};position:relative">
            ${isLead?`<div style="position:absolute;top:4px;right:6px;font-size:9px;color:${scenConf[sid]};font-weight:700">▶ 優勢</div>`:''}
            <div style="font-size:11px;font-weight:700;color:${scenConf[sid]};margin-bottom:4px">${scenLabel[sid]}</div>
            <div style="font-size:10px;color:#8b949e;margin-bottom:6px;line-height:1.3">${sc.summary||''}</div>
            <div style="display:flex;justify-content:space-between;align-items:center">
              <div style="font-size:12px;font-weight:700;font-family:monospace;color:${wTarget>=0?'#3fb950':'#f85149'}">${wTarget>=0?'+':''}${wTarget.toFixed(1)}%<span style="font-size:9px;color:#8b949e;font-weight:400;margin-left:2px">W${week}目標</span></div>
              <div style="font-size:13px;font-weight:700;color:${prob>=50?'#e6edf3':'#8b949e'}">${prob}%</div>
            </div>
            <div style="display:flex;gap:3px;margin-top:5px">${['w1','w2','w3','w4'].map(w=>`<div style="flex:1;text-align:center;background:#161b22;border-radius:3px;padding:2px 0"><div style="font-size:9px;color:#8b949e">${w.toUpperCase()}</div><div style="font-size:10px;font-family:monospace;color:${(sc[w+'_pct']||0)>=0?'#3fb950':'#f85149'}">${(sc[w+'_pct']||0)>=0?'+':''}${(sc[w+'_pct']||0).toFixed(0)}%</div></div>`).join('')}</div>
          </div>`;
        }).join('');
        s2=`<div style="margin-bottom:10px">
          <div style="font-size:10px;color:#f0b429;font-weight:600;margin-bottom:6px;text-transform:uppercase;letter-spacing:.6px">② 3シナリオ予測 <span style="color:#8b949e;font-weight:400;font-size:10px">分析チーム</span></div>
          <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px">${scenTiles}</div>
        </div>`;
      }
      // ③ 翌日仮説
      const h=curHyp.next_day_direction?curHyp:a.next_hypothesis;
      let s3='';
      if(h&&(h.next_day_direction||h.direction)){
        const dir=h.next_day_direction||h.direction||'?';
        const reason=h.next_day_reason||h.reason||'';
        const conf=h.next_day_confidence||h.confidence||'?';
        const keyLevel=h.next_day_key_level||h.key_level||'';
        s3=`<div style="margin-bottom:10px;padding:10px;background:#0d1117;border-radius:8px;border-left:3px solid ${dirColor[dir]||'#30363d'}">
          <div style="font-size:10px;color:#f0b429;font-weight:600;margin-bottom:6px;text-transform:uppercase;letter-spacing:.6px">③ 翌日仮説 <span style="color:#8b949e;font-weight:400">分析・検証チーム</span></div>
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
            <span style="font-size:16px;font-weight:700;color:${dirColor[dir]||'#e6edf3'}">${dirIcon[dir]||'?'} ${dir}</span>
            <span style="font-size:11px;padding:2px 8px;border-radius:4px;background:#21262d;color:${confColor[conf]||'#8b949e'}">確信度: ${conf}</span>
          </div>
          <div style="font-size:12px;color:#c9d1d9;line-height:1.5">${reason}</div>
          ${keyLevel?`<div style="font-size:11px;color:#f0b429;margin-top:4px">注目水準: ${keyLevel}</div>`:''}
        </div>`;
      } else {
        s3=`<div style="margin-bottom:10px;padding:10px;background:#0d1117;border-radius:8px;border-left:3px solid #30363d">
          <div style="font-size:10px;color:#f0b429;font-weight:600;margin-bottom:4px;text-transform:uppercase;letter-spacing:.6px">③ 翌日仮説</div>
          <div style="font-size:12px;color:#8b949e">仮説未生成（次回の平日に生成されます）</div>
        </div>`;
      }
      // ④ 差異分析 (daily_log v2 / hypothesis_history 旧)
      const dlog=a.daily_log||[];
      const hyph=a.hypothesis_history||[];
      let s4='';
      if(dlog.length>0){
        const recent=dlog.slice(-3).reverse();
        const matchCount=dlog.filter(d=>d.prev_match===true).length;
        const totalMatch=dlog.filter(d=>d.prev_match!==undefined&&d.prev_match!==null).length;
        const accStr=totalMatch>0?`${matchCount}/${totalMatch}回 (${Math.round(matchCount/totalMatch*100)}%)`:'---';
        const rows=recent.map(d=>{
          const dc=d.daily_pct||0;
          const ls=d.leading_scenario||'-';
          const lsColor=scenConf[ls]||'#8b949e';
          const matchIcon=d.prev_match===true?'<span style="color:#3fb950">○</span>':d.prev_match===false?'<span style="color:#f85149">×</span>':'<span style="color:#8b949e">-</span>';
          return `<tr>
            <td style="color:#8b949e;font-size:10px;white-space:nowrap">${d.date||'-'}</td>
            <td style="font-family:monospace;font-size:11px;color:${dc>=0?'#3fb950':'#f85149'};text-align:right">${dc>=0?'+':''}${dc.toFixed(2)}%</td>
            <td style="font-size:10px;color:${lsColor};text-align:center">${scenLabel[ls]||ls}</td>
            <td style="text-align:center">${matchIcon}</td>
            <td style="font-size:10px;color:#8b949e;max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${(d.cause||'').replace(/"/g,'&quot;')}">${d.cause||'-'}</td>
          </tr>`;
        }).join('');
        s4=`<div style="padding:10px;background:#0d1117;border-radius:8px;border-left:3px solid #388bfd">
          <div style="font-size:10px;color:#f0b429;font-weight:600;margin-bottom:6px;text-transform:uppercase;letter-spacing:.6px">④ 差異分析ログ <span style="color:#8b949e;font-weight:400">検証チーム</span> <span style="color:#3fb950;margin-left:8px">仮説的中: ${accStr}</span></div>
          <div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:11px">
            <thead><tr style="color:#8b949e;border-bottom:1px solid #30363d">
              <th style="text-align:left;padding:3px 4px">日付</th><th style="text-align:right;padding:3px 4px">騰落</th><th style="text-align:center;padding:3px 4px">リード</th><th style="text-align:center;padding:3px 4px">的中</th><th style="text-align:left;padding:3px 4px">要因</th>
            </tr></thead>
            <tbody>${rows}</tbody>
          </table></div>
          ${dlog.length>3?`<div style="font-size:10px;color:#8b949e;margin-top:4px;text-align:right">直近3件表示（全${dlog.length}件）</div>`:''}
        </div>`;
      } else if(hyph.length>0){
        // 旧フォーマット後方互換
        const latest=hyph[hyph.length-1];
        s4=`<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
          <div style="padding:10px;background:#0d1117;border-radius:8px;border-left:3px solid ${dirColor[latest.actual_direction]||'#30363d'}">
            <div style="font-size:10px;color:#f0b429;font-weight:600;margin-bottom:6px;text-transform:uppercase;letter-spacing:.6px">④ 実際の動き</div>
            <div style="font-size:16px;font-weight:700;color:${dirColor[latest.actual_direction]||'#e6edf3'}">${dirIcon[latest.actual_direction]||'?'} ${latest.actual_direction||'?'}</div>
            <div style="font-size:13px;font-family:monospace;margin-top:4px;color:${(latest.price_change_pct||0)>=0?'#3fb950':'#f85149'}">${(latest.price_change_pct||0)>=0?'+':''}${(latest.price_change_pct||0).toFixed(2)}%</div>
          </div>
          <div style="padding:10px;background:#0d1117;border-radius:8px;border-left:3px solid ${latest.match?'#3fb950':'#f85149'}">
            <div style="font-size:10px;color:#f0b429;font-weight:600;margin-bottom:6px;text-transform:uppercase;letter-spacing:.6px">差異分析</div>
            <div style="font-size:18px;font-weight:700;color:${latest.match?'#3fb950':'#f85149'}">${latest.match?'○ 的中':'× 外れ'}</div>
            ${hyph.length>1?`<div style="font-size:10px;color:#8b949e;margin-top:4px">直近${Math.min(hyph.length,5)}回的中率: ${Math.round(hyph.slice(-5).filter(x=>x.match).length/Math.min(hyph.length,5)*100)}%</div>`:''}
          </div>
        </div>`;
      } else {
        s4=`<div style="padding:10px;background:#0d1117;border-radius:8px;border-left:3px solid #30363d">
          <div style="font-size:10px;color:#f0b429;font-weight:600;margin-bottom:4px;text-transform:uppercase;letter-spacing:.6px">④ 差異分析</div>
          <div style="font-size:12px;color:#8b949e">翌日結果待ち（仮説生成後の翌営業日に更新）</div>
        </div>`;
      }
      return `<div class="sim-card">${s1}${s2}${s3}${s4}</div>`;
    }).join('');
  }
  // 履歴（簡易表）
  document.getElementById("sim-hist-count").textContent=history.length+"件";
  const tbody=document.getElementById("sim-hist-body");
  if(history.length===0){tbody.innerHTML='<tr><td colspan="8" style="text-align:center;color:#8b949e;padding:20px">履歴なし</td></tr>';return;}
  tbody.innerHTML=history.map(h=>{
    const pct=h.result_pct||0;const cls=pct>0?'pos':pct<0?'neg':'neu';const res=h.result||'-';
    return `<tr><td class="name">${h.name||'-'}</td><td class="code">${h.code||'-'}</td><td class="r">${(h.entry_price||0).toLocaleString()}</td><td class="r">${(h.current_price||h.entry_price||0).toLocaleString()}</td><td class="r ${cls}" style="font-family:monospace">${pct>=0?'+':''}${pct.toFixed(1)}%</td><td><span class="sim-result-badge ${resultCls[res]||''}">${resultLabel[res]||res}</span></td><td style="color:#8b949e">${h.days_elapsed||0}日</td><td style="color:#8b949e">${h.start_date||'-'}</td></tr>`;
  }).join('');
}
function initSim(code,finsRecords){
  simCode=code;
  var fyRecords=dedupFY(finsRecords.filter(function(r){return r.period==='FY';}));
  if(!fyRecords.length){document.getElementById('sim-section').style.display='none';return;}
  var last=fyRecords[fyRecords.length-1];
  var prev=fyRecords.length>=2?fyRecords[fyRecords.length-2]:null;
  var s=allData.find(function(x){return x.code===code;})||{};
  simBaseData={
    sales:last.sales||0,
    op:last.op||0,
    np:last.np||0,
    eps:last.eps||0,
    price:s.price||0,
    sharesEst:last.eps&&last.np?Math.round(last.np/last.eps):0,
  };
  // Calculate defaults from actuals
  var cagr=0;
  if(fyRecords.length>=2&&fyRecords[0].sales>0&&last.sales>0){
    cagr=((Math.pow(last.sales/fyRecords[0].sales,1/(fyRecords.length-1))-1)*100);
  }
  var opMargin=last.sales>0?(last.op/last.sales*100):0;
  var npMargin=last.sales>0?(last.np/last.sales*100):0;
  var curPER=last.eps>0&&s.price?(s.price/last.eps):20;

  // Load saved settings or use defaults
  var saved=null;
  try{saved=JSON.parse(localStorage.getItem('sim_'+code));}catch(e){}
  document.getElementById('sim-growth').value=saved?saved.growth:Math.round(cagr);
  document.getElementById('sim-opmargin').value=saved?saved.opMargin:Math.round(opMargin);
  document.getElementById('sim-npmargin').value=saved?saved.npMargin:Math.round(npMargin);
  document.getElementById('sim-per').value=saved?saved.per:Math.round(curPER);
  document.getElementById('sim-years').value=saved?saved.years:3;
  document.getElementById('sim-unit-price').value=saved?saved.unitPrice||0:0;
  document.getElementById('sim-volume').value=saved?saved.volume||0:0;
  document.getElementById('sim-cogs').value=saved?saved.cogs||60:60;
  document.getElementById('sim-headcount').value=saved?saved.headcount||0:0;
  document.getElementById('sim-salary').value=saved?saved.salary||0:0;
  document.getElementById('sim-section').style.display='block';
  setTimeout(function(){runSim();},100);
}
function runSim(){
  if(!simBaseData||!simBaseData.sales)return;
  var growth=parseFloat(document.getElementById('sim-growth').value)||0;
  var opMargin=parseFloat(document.getElementById('sim-opmargin').value)||0;
  var npMargin=parseFloat(document.getElementById('sim-npmargin').value)||0;
  var per=parseFloat(document.getElementById('sim-per').value)||20;
  var years=parseInt(document.getElementById('sim-years').value)||3;
  var unitPrice=parseFloat(document.getElementById('sim-unit-price').value)||0;
  var volume=parseFloat(document.getElementById('sim-volume').value)||0;
  var cogs=parseFloat(document.getElementById('sim-cogs').value)||60;
  var headcount=parseFloat(document.getElementById('sim-headcount').value)||0;
  var salary=parseFloat(document.getElementById('sim-salary').value)||0;
  var curPrice=simBaseData.price||0;
  var sharesEst=simBaseData.sharesEst||1;

  // If unit price and volume are set, use bottom-up sales calc
  var useBottomUp=unitPrice>0&&volume>0;

  var h='';
  // Show cost breakdown if detailed KPIs are set
  if(useBottomUp||headcount>0){
    h+='<div class="fins-section" style="margin-bottom:10px"><div class="fins-section-title">KPI分解</div><div style="display:flex;gap:8px;flex-wrap:wrap">';
    if(useBottomUp)h+='<div class="detail-card" style="flex:1;min-width:120px"><div class="detail-card-label">売上(単価×数量)</div><div class="detail-card-value" style="font-size:14px">'+fmtYen(unitPrice*10000*volume*10000)+'</div></div>';
    h+='<div class="detail-card" style="flex:1;min-width:120px"><div class="detail-card-label">原価('+cogs+'%)</div><div class="detail-card-value" style="font-size:14px">'+fmtYen(simBaseData.sales*cogs/100)+'</div></div>';
    if(headcount>0&&salary>0)h+='<div class="detail-card" style="flex:1;min-width:120px"><div class="detail-card-label">人件費('+headcount+'人×'+salary+'万)</div><div class="detail-card-value" style="font-size:14px">'+fmtYen(headcount*salary*10000)+'</div></div>';
    h+='</div></div>';
  }

  h+='<div class="table-wrap"><table class="fins-table"><thead><tr><th>年度</th><th>予想売上</th><th>予想営業利益</th><th>予想純利益</th><th>予想EPS</th><th>適正株価</th><th>乖離率</th></tr></thead><tbody>';
  h+='<tr><td style="color:#8b949e">現在</td><td>'+fmtYen(simBaseData.sales)+'</td><td>'+fmtYen(simBaseData.op)+'</td><td>'+fmtYen(simBaseData.np)+'</td><td>'+fmtNum(simBaseData.eps,1)+'</td><td>'+Number(Math.round(curPrice)).toLocaleString()+'</td><td>-</td></tr>';

  for(var y=1;y<=years;y++){
    var fSales;
    if(useBottomUp){
      fSales=unitPrice*10000*volume*10000*Math.pow(1+growth/100,y);
    }else{
      fSales=simBaseData.sales*Math.pow(1+growth/100,y);
    }
    var fOp=fSales*opMargin/100;
    var fNp=fSales*npMargin/100;
    var fEps=sharesEst>0?(fNp/sharesEst):0;
    var targetPrice=fEps*per;
    var gap=curPrice>0?((targetPrice/curPrice-1)*100):0;
    var gapClass=gap>=0?'pos':'neg';
    h+='<tr class="forecast"><td>'+y+'年後</td><td>'+fmtYen(fSales)+'</td><td>'+fmtYen(fOp)+'</td><td>'+fmtYen(fNp)+'</td><td>'+fmtNum(fEps,1)+'</td><td class="'+gapClass+'">'+Number(Math.round(targetPrice)).toLocaleString()+'</td><td class="'+gapClass+'">'+(gap>=0?'+':'')+gap.toFixed(1)+'%</td></tr>';
  }
  h+='</tbody></table></div>';

  // PER scenario
  var fEpsFinal;
  if(useBottomUp){fEpsFinal=unitPrice*10000*volume*10000*Math.pow(1+growth/100,years)*npMargin/100/sharesEst;}
  else{fEpsFinal=simBaseData.sales*Math.pow(1+growth/100,years)*npMargin/100/sharesEst;}
  var scenarios=[
    {label:'悲観 (PER '+(Math.round(per*0.7))+')',per:per*0.7},
    {label:'基準 (PER '+Math.round(per)+')',per:per},
    {label:'楽観 (PER '+(Math.round(per*1.3))+')',per:per*1.3},
  ];
  h+='<div style="margin-top:12px"><div class="fins-section-title">PERシナリオ分析（'+years+'年後）</div>';
  h+='<div style="display:flex;gap:10px">';
  scenarios.forEach(function(sc){
    var tp=fEpsFinal*sc.per;
    var ret=curPrice>0?((Math.pow(tp/curPrice,1/years)-1)*100):0;
    var cls=ret>=0?'green':'red';
    h+='<div class="detail-card" style="flex:1"><div class="detail-card-label">'+sc.label+'</div><div class="detail-card-value '+cls+'">'+Number(Math.round(tp)).toLocaleString()+'円</div><div style="font-size:11px;color:#8b949e">年率 '+(ret>=0?'+':'')+ret.toFixed(1)+'%</div></div>';
  });
  h+='</div></div>';

  document.getElementById('sim-result').innerHTML=h;
}
function saveSim(){
  if(!simCode)return;
  var d={
    growth:parseFloat(document.getElementById('sim-growth').value)||0,
    opMargin:parseFloat(document.getElementById('sim-opmargin').value)||0,
    npMargin:parseFloat(document.getElementById('sim-npmargin').value)||0,
    per:parseFloat(document.getElementById('sim-per').value)||20,
    years:parseInt(document.getElementById('sim-years').value)||3,
    unitPrice:parseFloat(document.getElementById('sim-unit-price').value)||0,
    volume:parseFloat(document.getElementById('sim-volume').value)||0,
    cogs:parseFloat(document.getElementById('sim-cogs').value)||60,
    headcount:parseFloat(document.getElementById('sim-headcount').value)||0,
    salary:parseFloat(document.getElementById('sim-salary').value)||0,
  };
  localStorage.setItem('sim_'+simCode,JSON.stringify(d));
  alert('シミュレーション設定を保存しました: '+simCode);
}

// AI-based simulation from mid-term plan
async function aiSim(){
  if(!simCode)return;
  var s=allData.find(function(x){return x.code===simCode;})||{};
  var name=s.name||simCode;
  var prompt="日本株「"+name+"（"+simCode+"）」の中期経営計画から、以下の数値を抽出してJSON形式で返してください。見つからない場合は妥当な推定値を入れて、推定値には estimated:true を付けてください。\n\nJSON形式:\n{\"growth\": 売上成長率(年率%), \"opMargin\": 営業利益率%, \"npMargin\": 純利益率%, \"per\": 適正PER倍, \"years\": 計画年数, \"source\": \"計画名\", \"notes\": \"補足\"}\n\nJSONのみ返してください。";
  try{
    var res=await fetch(GEMINI_API,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({model:"gemini-2.5-flash",contents:[{parts:[{text:prompt}]}],tools:[{google_search:{}}]})});
    var data=await res.json();
    var text=data.candidates?.[0]?.content?.parts?.[0]?.text||"";
    // Extract JSON from response
    var match=text.match(/\{[\s\S]*\}/);
    if(match){
      var parsed=JSON.parse(match[0]);
      if(parsed.growth!=null)document.getElementById("sim-growth").value=Math.round(parsed.growth);
      if(parsed.opMargin!=null)document.getElementById("sim-opmargin").value=Math.round(parsed.opMargin);
      if(parsed.npMargin!=null)document.getElementById("sim-npmargin").value=Math.round(parsed.npMargin);
      if(parsed.per!=null)document.getElementById("sim-per").value=Math.round(parsed.per);
      if(parsed.years!=null)document.getElementById("sim-years").value=parsed.years;
      runSim();
      alert("中期計画ベースで設定しました"+(parsed.source?" ("+parsed.source+")":"")+(parsed.notes?"\n"+parsed.notes:""));
    }else{alert("中期計画データを解析できませんでした:\n"+text.slice(0,200));}
  }catch(e){alert("エラー: "+e.message);}
}

// Earnings backtest: compare past forecasts vs actuals
function runBacktest(){
  if(!simCode)return;
  var fd=window._finsData||{};
  var records=fd[simCode];
  if(!records||!records.length){document.getElementById("backtest-result").innerHTML='<div style="color:#f85149;margin-top:8px">業績データがありません</div>';return;}
  var fyRecords=dedupFY(records.filter(function(r){return r.period==="FY";}));
  if(fyRecords.length<2){return;}
  var h='<div class="fins-section" style="margin-top:16px"><div class="fins-section-title">業績予想バックテスト（予想 vs 実績）</div>';
  h+='<div class="table-wrap"><table class="fins-table"><thead><tr><th>決算期</th><th>予想売上</th><th>実績売上</th><th>乖離</th><th>予想EPS</th><th>実績EPS</th><th>乖離</th></tr></thead><tbody>';
  for(var i=1;i<fyRecords.length;i++){
    var cur=fyRecords[i];
    var prev=fyRecords[i-1];
    // Previous period's forecast for this period
    var fSales=prev.f_sales;var fEps=prev.f_eps;
    var aSales=cur.sales;var aEps=cur.eps;
    var salesDev=fSales&&aSales?((aSales-fSales)/fSales*100):null;
    var epsDev=fEps&&aEps?((aEps-fEps)/fEps*100):null;
    h+='<tr><td>'+cur.fy+'</td>';
    h+='<td>'+fmtYen(fSales)+'</td><td>'+fmtYen(aSales)+'</td>';
    h+='<td class="'+(salesDev!=null?(salesDev>=0?"pos":"neg"):"")+'">'+( salesDev!=null?(salesDev>=0?"+":"")+salesDev.toFixed(1)+"%":"-")+'</td>';
    h+='<td>'+fmtNum(fEps,1)+'</td><td>'+fmtNum(aEps,1)+'</td>';
    h+='<td class="'+(epsDev!=null?(epsDev>=0?"pos":"neg"):"")+'">'+( epsDev!=null?(epsDev>=0?"+":"")+epsDev.toFixed(1)+"%":"-")+'</td>';
    h+='</tr>';
  }
  h+='</tbody></table></div></div>';
  document.getElementById("backtest-result").innerHTML=h;
}

// === Feature: Position Size Calculator ===
function initPosCalc(){
  ['ps-account','ps-risk','ps-entry','ps-stop'].forEach(function(id){
    document.getElementById(id).addEventListener('input',calcPositionSize);
  });
  var cashVal=loadCash();
  if(cashVal)document.getElementById('ps-account').value=cashVal;
}
function calcPositionSize(){
  var account=parseFloat(document.getElementById('ps-account').value)||0;
  var riskPct=parseFloat(document.getElementById('ps-risk').value)||0;
  var entry=parseFloat(document.getElementById('ps-entry').value)||0;
  var stop=parseFloat(document.getElementById('ps-stop').value)||0;
  var el=document.getElementById('ps-result');
  if(!account||!entry||!stop||entry<=stop||riskPct<=0){el.textContent='入力してください（エントリー > 損切り）';return;}
  var riskAmount=account*(riskPct/100);
  var riskPerShare=entry-stop;
  var shares=Math.floor(riskAmount/riskPerShare);
  var totalCost=shares*entry;
  var pctOfAccount=account>0?(totalCost/account*100).toFixed(1):'0';
  el.innerHTML='<b style="color:#f0b429">'+shares+'株</b>購入可能 | リスク金額: <span style="color:#f85149">'+Number(Math.round(shares*riskPerShare)).toLocaleString()+'円</span> ('+riskPct+'%) | 総コスト: '+Number(Math.round(totalCost)).toLocaleString()+'円 (資金の'+pctOfAccount+'%)';
}

// === Feature: Volume Analysis ===
