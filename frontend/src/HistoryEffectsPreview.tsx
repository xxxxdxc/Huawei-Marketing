import HistoryPage from './HistoryPage';
export default function HistoryEffectsPreview(){
  return <main className="history-preview-page" id="main-content"><header className="history-preview-toolbar"><span>华为 PC · 效果与经验学习原型</span><a className="secondary" href="/">返回实际工作台</a></header><HistoryPage tasks={[]} pending={false} initialMode="effects" onOpenTask={()=>{}} onNewTask={()=>{location.href='/';}} /></main>;
}
