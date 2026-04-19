function loadChart(){
  var code=(document.getElementById('chart-code-input')||{}).value||'';
  code=code.trim();
  if(!code){alert('銘柄コードを入力してください');return;}
  var found=allData.find(function(x){return x.code===code;});
  if(!found){
    document.getElementById('chart-error').style.display='block';
    document.getElementById('chart-error').textContent='銘柄が見つかりません: '+code;
    return;
  }
  var cd=window._chartData||{};
  var ohlcv=cd[code];
  if(!ohlcv||!ohlcv.length){
    document.getElementById('chart-error').style.display='block';
    document.getElementById('chart-error').textContent='チャートデータがありません: '+code+' （年初来高値圏/監視/PF銘柄のみ対応。Claude Desktopで export_chart_data(extra_codes=\"'+code+'\") を実行すると追加できます）';
    return;
  }
  document.getElementById('chart-error').style.display='none';
  document.getElementById('chart-stock-name').textContent=code+' '+found.name+' | 株価: '+Number(found.price).toLocaleString()+' | スコア: '+found.score;

  // Pattern info
  var pat=window._patternData||{};
  var sp=pat[code];
  var patEl=document.getElementById('chart-patterns');
  if(sp&&sp.patterns&&sp.patterns.length){
    patEl.innerHTML=sp.patterns.map(function(p){
      var cls=p==="cup_with_handle"?"pattern-cup":p==="vcp"?"pattern-vcp":"pattern-flat";
      var lbl=p==="cup_with_handle"?"Cup with Handle":p==="vcp"?"VCP":"Flat Base";
      var det=sp.details[p]||{};
      var reason=det.reason||"";
      return'<div style="margin-bottom:4px"><span class="pattern-badge '+cls+'" style="font-size:12px;padding:3px 8px">'+lbl+'</span>'+(reason?' <span style="font-size:11px;color:#8b949e;margin-left:4px">'+reason+'</span>':'')+'</div>';
    }).join("");
  }else{patEl.innerHTML='';}

  // Legend
  var price=found.price,sma50v=found.sma50||price,sma150v=found.sma150||price,sma200v=found.sma200||price;
  document.getElementById('chart-legend').innerHTML=
    '<span style="font-size:11px;color:#e6edf3">現在値: <b>'+Number(price).toLocaleString()+'</b></span>'+
    '<span style="font-size:11px;color:#2196F3;margin-left:10px">SMA50: '+Number(sma50v.toFixed(0)).toLocaleString()+'</span>'+
    '<span style="font-size:11px;color:#FF9800;margin-left:10px">SMA150: '+Number(sma150v.toFixed(0)).toLocaleString()+'</span>'+
    '<span style="font-size:11px;color:#9C27B0;margin-left:10px">SMA200: '+Number(sma200v.toFixed(0)).toLocaleString()+'</span>';

  // Prepare data (resample if needed)
  var rawData=ohlcv;
  if(curTF==='weekly')rawData=resampleWeekly(ohlcv);
  else if(curTF==='monthly')rawData=resampleMonthly(ohlcv);
  var candles=rawData.map(function(d){return{time:d.time,open:d.open,high:d.high,low:d.low,close:d.close};});
  var volumes=rawData.map(function(d){return{time:d.time,value:d.volume,color:d.close>=d.open?'rgba(38,166,154,0.5)':'rgba(239,83,80,0.5)'};});

  // Compute SMAs
  var closes=rawData.map(function(d){return d.close;});
  function calcSMA(data,period){
    var result=[];
    for(var i=0;i<data.length;i++){
      if(i<period-1){continue;}
      var sum=0;for(var j=i-period+1;j<=i;j++)sum+=closes[j];
      result.push({time:rawData[i].time,value:sum/period});
    }
    return result;
  }
  var smaPeriods=curTF==='daily'?[50,150,200]:curTF==='weekly'?[10,30,40]:[3,7,10];
  var sma50d=calcSMA(closes,smaPeriods[0]);
  var sma150d=calcSMA(closes,smaPeriods[1]);
  var sma200d=calcSMA(closes,smaPeriods[2]);

  // Create or recreate chart
  var container=document.getElementById('chart-container');
  container.innerHTML='';
  lwChart=LightweightCharts.createChart(container,{
    width:container.clientWidth,
    height:400,
    layout:{background:{type:'solid',color:'#0d1117'},textColor:'#8b949e'},
    grid:{vertLines:{color:'#161b22'},horzLines:{color:'#161b22'}},
    crosshair:{mode:0},
    rightPriceScale:{borderColor:'#30363d'},
    timeScale:{borderColor:'#30363d',timeVisible:false},
  });

  candleSeries=lwChart.addCandlestickSeries({
    upColor:'#26a69a',downColor:'#ef5350',borderUpColor:'#26a69a',borderDownColor:'#ef5350',
    wickUpColor:'#26a69a',wickDownColor:'#ef5350',
  });
  candleSeries.setData(candles);

  volumeSeries=lwChart.addHistogramSeries({
    priceFormat:{type:'volume'},priceScaleId:'vol',
  });
  volumeSeries.priceScale().applyOptions({scaleMargins:{top:0.8,bottom:0}});
  volumeSeries.setData(volumes);

  sma50Series=lwChart.addLineSeries({color:'#2196F3',lineWidth:1,priceLineVisible:false,lastValueVisible:false});
  sma50Series.setData(sma50d);
  sma150Series=lwChart.addLineSeries({color:'#FF9800',lineWidth:1,priceLineVisible:false,lastValueVisible:false});
  sma150Series.setData(sma150d);
  sma200Series=lwChart.addLineSeries({color:'#9C27B0',lineWidth:1,priceLineVisible:false,lastValueVisible:false});
  sma200Series.setData(sma200d);

  // Pattern pivot lines
  if(sp&&sp.details){
    Object.keys(sp.details).forEach(function(pname){
      var det=sp.details[pname];
      if(det&&det.details){
        var pivot=det.details.pivot_price||det.details.resistance;
        if(pivot){
          var lbl=pname==="cup_with_handle"?"CwH Pivot":pname==="vcp"?"VCP Resist":"Flat Resist";
          candleSeries.createPriceLine({price:pivot,color:'#f0b429',lineWidth:1,lineStyle:2,axisLabelVisible:true,title:lbl});
        }
      }
    });
  }

  lwChart.timeScale().fitContent();
  window.addEventListener('resize',function(){if(lwChart)lwChart.applyOptions({width:container.clientWidth});});
  analyzeVolume(ohlcv);
  renderStockTrend(ohlcv);
  idxCompareKey='';idxCompareSeries=null;var ics=document.getElementById('idx-compare-select');if(ics)ics.value='';
}
function openChart(code){
  showPage('chart',document.querySelectorAll('.nav-btn')[1]);
  document.getElementById('chart-code-input').value=code;
  loadChart();
}
const DATA_BASE="https://raw.githubusercontent.com/yangpinggaoye15-dotcom/invest-data/main/";
const CHART_DATA_URL=DATA_BASE+"chart_data.json";
const PATTERN_DATA_URL=DATA_BASE+"pattern_data.json";
const WATCHLIST_URL=DATA_BASE+"watchlist.json";
const PORTFOLIO_URL=DATA_BASE+"portfolio.json";
window._chartData={};window._patternData={};window._watchlist={};window._portfolio={};
function switchTF(tf){
  curTF=tf;
  ['daily','weekly','monthly'].forEach(function(t){
    var b=document.getElementById('tf-'+t);
    if(!b)return;
    if(t===tf){b.style.background='#f0b429';b.style.color='#0d1117';b.style.borderColor='#f0b429';b.style.fontWeight='600';}
    else{b.style.background='none';b.style.color='#8b949e';b.style.borderColor='#30363d';b.style.fontWeight='400';}
  });
  loadChart();
}
function resampleWeekly(data){
  var weeks={};
  data.forEach(function(d){
    var dt=new Date(d.time);
    var fri=new Date(dt);fri.setDate(dt.getDate()+(5-dt.getDay()+7)%7);
    var key=fri.toISOString().slice(0,10);
    if(!weeks[key])weeks[key]={time:key,open:d.open,high:d.high,low:d.low,close:d.close,volume:d.volume};
    else{weeks[key].high=Math.max(weeks[key].high,d.high);weeks[key].low=Math.min(weeks[key].low,d.low);weeks[key].close=d.close;weeks[key].volume+=d.volume;}
  });
  return Object.values(weeks).sort(function(a,b){return a.time.localeCompare(b.time);});
}
function resampleMonthly(data){
  var months={};
  data.forEach(function(d){
    var key=d.time.slice(0,7)+"-01";
    if(!months[key])months[key]={time:key,open:d.open,high:d.high,low:d.low,close:d.close,volume:d.volume};
    else{months[key].high=Math.max(months[key].high,d.high);months[key].low=Math.min(months[key].low,d.low);months[key].close=d.close;months[key].volume+=d.volume;}
  });
  return Object.values(months).sort(function(a,b){return a.time.localeCompare(b.time);});
}

// Pattern filter
var patOn=false;
function renderStockTrend(ohlcv){
  var el=document.getElementById('chart-trend-badge');if(!el)return;
  if(!ohlcv||ohlcv.length<200){el.innerHTML='';return;}
  var closes=ohlcv.map(function(d){return d.close;});
  var t=calcTrend(closes);
  el.innerHTML='<span class="trend-badge '+t.cls+'">'+t.label+'</span>';
}

// === Feature: Index vs Stock Comparison ===
var idxCompareSeries=null,idxCompareKey='';
