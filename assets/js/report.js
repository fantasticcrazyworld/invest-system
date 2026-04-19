function initReportPage(){
  if(reportPageInited)return;
  reportPageInited=true;
  // 直近14日のナビボタン生成
  const nav=document.getElementById('report-date-nav');
  const today=new Date();
  let html='';
  for(let i=0;i<14;i++){
    const d=new Date(today);d.setDate(today.getDate()-i);
    const ds=d.toISOString().slice(0,10);
    html+=`<button class="report-date-btn" onclick="loadDateReport('${ds}',this)">${ds.slice(5)}</button>`;
  }
  nav.innerHTML=html;
  loadReport('latest_report');
}
async function loadReport(filename,fallbackFilename){
  const el=document.getElementById('report-body');
  el.innerHTML='<div class="loading"><div class="spinner"></div><div class="loading-text">読み込み中...</div></div>';
  try{
    const url=REPORT_BASE+(filename.endsWith('.md')?filename:filename+'.md')+'?t='+Date.now();
    const r=await fetch(url);
    if(!r.ok)throw new Error('HTTP '+r.status);
    el.innerHTML=mdToHtml(await r.text());
  }catch(e){
    if(fallbackFilename){
      try{
        const url2=REPORT_BASE+(fallbackFilename.endsWith('.md')?fallbackFilename:fallbackFilename+'.md')+'?t='+Date.now();
        const r2=await fetch(url2);
        if(!r2.ok)throw new Error('HTTP '+r2.status);
        el.innerHTML='<div style="font-size:11px;color:#f0b429;padding:6px 14px;border-bottom:1px solid #21262d;background:#1a1500">⚠ このレポートはまだ生成されていません。最新のレポートを表示しています。</div>'+mdToHtml(await r2.text());
        return;
      }catch(e2){}
    }
    el.innerHTML='<div class="error-box">読み込み失敗: '+e.message+'</div>';
  }
}
function selectReportTeam(team,btn){
  currentReportTeam=team;currentReportDate='';
  document.querySelectorAll('.report-team-btn').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  document.querySelectorAll('.report-date-btn').forEach(b=>b.classList.remove('active'));
  loadReport(team);
}
async function loadReportWithFallback(primary,fallback){
  const el=document.getElementById('report-body');
  el.innerHTML='<div class="loading"><div class="spinner"></div><div class="loading-text">読み込み中...</div></div>';
  try{
    const url=REPORT_BASE+(primary.endsWith('.md')?primary:primary+'.md')+'?t='+Date.now();
    const r=await fetch(url);
    if(!r.ok)throw new Error('HTTP '+r.status);
    el.innerHTML=mdToHtml(await r.text());
  }catch(e){
    // フォールバック: 最新版を表示
    try{
      const url2=REPORT_BASE+(fallback.endsWith('.md')?fallback:fallback+'.md')+'?t='+Date.now();
      const r2=await fetch(url2);
      if(!r2.ok)throw new Error('HTTP '+r2.status);
      el.innerHTML='<div style="font-size:11px;color:#8b949e;padding:6px 14px;border-bottom:1px solid #21262d">※ '+date+'のレポートが見つからないため最新版を表示しています</div>'+mdToHtml(await r2.text());
    }catch(e2){
      el.innerHTML='<div class="error-box">読み込み失敗: '+e2.message+'</div>';
    }
  }
}
function loadDateReport(date,btn){
  currentReportDate=date;
  document.querySelectorAll('.report-date-btn').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  const activeTeam=currentReportTeam||'latest_report';
  const isIntegrated=activeTeam==='latest_report'||activeTeam==='report';
  if(isIntegrated){
    // 統合レポートタブ → 日付付き統合レポート（なければlatest_reportにフォールバック）
    loadReport(date+'_daily_report','latest_report');
  }else{
    // チームタブ → 日付付きチームレポート（なければ最新版にフォールバック）
    loadReportWithFallback(date+'_'+activeTeam, activeTeam);
  }
}
const SIM_URL="https://raw.githubusercontent.com/yangpinggaoye15-dotcom/invest-data/main/reports/simulation_log.json";
const KPI_LOG_URL="https://raw.githubusercontent.com/yangpinggaoye15-dotcom/invest-data/main/reports/kpi_log.json";
const TEAM_KPI_NAMES={info:'情報収集',analysis:'銘柄選定・仮説',risk:'リスク管理',strategy:'投資戦略',report:'レポート統括',verification:'検証',security:'セキュリティ',audit:'内部監査'};
function renderTeamKpiSection(kpiLog){
  const el=document.getElementById('team-kpi-table');
  if(!kpiLog||!kpiLog.length){el.innerHTML='<div style="padding:20px;color:#8b949e;text-align:center">KPIデータなし（初回実行後に表示されます）</div>';return;}
  const latest=kpiLog[kpiLog.length-1];
  const prev7=kpiLog.slice(-7);
  document.getElementById('team-kpi-date').textContent=latest.date||'-';
  const teams=Object.keys(TEAM_KPI_NAMES);
  const firstScores=Object.values(latest.teams||{})[0]||{};
  const kpiKeys=Object.keys(firstScores);
  let html='<table><thead><tr><th>チーム</th><th class="r">本日</th><th class="r">7日平均</th><th class="r">推移</th>';
  kpiKeys.forEach(k=>{html+=`<th class="r" style="font-size:10px;color:#8b949e">${k}</th>`;});
  html+='</tr></thead><tbody>';
  teams.forEach(key=>{
    const scores=latest.teams?.[key]||{};
    const vals=Object.values(scores).filter(v=>typeof v==='number');
    const avg=vals.length?vals.reduce((a,b)=>a+b,0)/vals.length:null;
    const hist7=prev7.map(e=>{const s=e.teams?.[key]||{};const v=Object.values(s).filter(v=>typeof v==='number');return v.length?v.reduce((a,b)=>a+b,0)/v.length:null;}).filter(v=>v!==null);
    const avg7=hist7.length?hist7.reduce((a,b)=>a+b,0)/hist7.length:null;
    const trend=avg!==null&&avg7!==null?(avg>avg7+0.3?'↑':avg<avg7-0.3?'↓':'→'):'-';
    const tc=trend==='↑'?'#3fb950':trend==='↓'?'#f85149':'#8b949e';
    const sc=avg===null?'#8b949e':avg>=7?'#3fb950':avg>=5?'#f0b429':'#f85149';
    html+=`<tr><td style="font-size:12px">${TEAM_KPI_NAMES[key]||key}</td><td class="r" style="font-weight:700;color:${sc}">${avg!==null?avg.toFixed(1):'-'}</td><td class="r" style="color:#8b949e;font-size:12px">${avg7!==null?avg7.toFixed(1):'-'}</td><td class="r" style="color:${tc};font-weight:700;font-size:14px">${trend}</td>`;
    kpiKeys.forEach(k=>{const v=scores[k];const vc=v===undefined?'#8b949e':v>=7?'#3fb950':v>=5?'#f0b429':'#f85149';html+=`<td class="r" style="color:${vc};font-size:12px">${v!==undefined?v:'-'}</td>`;});
    html+='</tr>';
  });
  html+='</tbody></table>';
  el.innerHTML=html;
}
let simLoaded=false,simLog=null;
