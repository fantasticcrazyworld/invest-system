
loadData();loadChartData();loadPatternData();loadFinsData();loadTimeline();loadKnowledge();loadWatchlist();loadPortfolio();loadIndexData();renderPresets();setTimeout(loadCash,500);setTimeout(function(){initPosCalc();renderSectorDist();},1000);
if('serviceWorker' in navigator){navigator.serviceWorker.register('sw.js').catch(function(){});}
