export type DemoPlatform = 'xiaohongshu' | 'wechat' | 'moments';
export type DemoContext = 'campus' | 'office' | 'travel';
export type CaseLessons = { title: string; opening: string; structure: string[]; voice: string; cta: string };
export type DemoPost = { id: string; campaignId: DemoContext; platform: DemoPlatform; title: string; lead: string; paragraphs: string[]; cta: string; tags: string[]; images: string[]; publishedAt: string; observedAt: string; metrics: { views: number | null; likes: number; saves: number | null; comments: number }; lessons: CaseLessons };
export type DemoCampaign = { id: DemoContext; name: string; audience: string; scene: string; date: string; posts: DemoPost[] };

const stories = [
  { id: 'campus' as const, name: '开学季 · MateBook 推广', audience: '大学新生', scene: '开学购机', date: '2026-10-18',
    title: '开学选电脑，先把这三件小事想清楚', opening: '从一张具体的学习任务清单切入，降低选购话题的距离感。',
    lead: '新学期的电脑要陪你做什么？先别急着列参数，把课堂、作业和小组展示写下来。',
    paragraphs: ['第一步，列出会用的软件和文件。课堂记录、课程作业、小组汇报，需求不同，选购时该确认的事情也不同。', '第二步，带着自己的任务核对具体机型资料。型号、配置和软件适配逐项确认，不把某一款的说明套用到全部产品。', '第三步，把拿不准的环节留给到店体验。试着打开常用文件、敲一段文字，再判断是否适合自己的学习日常。'],
    short: '开学选电脑，可以先列一张学习清单：常用软件、课程作业、小组展示。带着清单核对具体机型，再用自己的文件到店试一试。',
    structure: ['学习任务清单', '具体机型的核对标准', '带着文件到店体验'], voice: '像学长学姐给建议，用具体动作代替笼统推荐。', cta: '邀请读者带着课程需求咨询或到店体验，不承诺未核实权益。',
  },
  { id: 'office' as const, name: '职场第一台 · 办公场景推广', audience: '职场新人', scene: '日常办公', date: '2026-10-19',
    title: '第一台办公电脑，从你的工作清单开始选', opening: '用入职后会遇到的具体工作，引出选购标准。',
    lead: '第一次选办公电脑，先想清楚每天需要处理什么，比照着别人的配置清单下单更有方向。',
    paragraphs: ['把常用的文档、会议材料和业务软件列出来，区分每天都会做的事与偶尔出现的任务。', '对照具体机型资料，确认配置、接口与软件适用条件。对复杂文件的处理感受，需要用自己的任务来验证。', '到店时可以带上常用文件，实际看看显示效果、文字输入和连接方式，再作选择。'],
    short: '准备选第一台办公电脑？先列出每天会用的软件、文件和外设。核对具体机型，再带一份常用材料到店体验，选择会更有方向。',
    structure: ['新人工作场景', '高频任务与核对项目', '可执行的体验建议'], voice: '清晰、平实，给出可以直接照着做的核对步骤。', cta: '邀请读者带常用材料咨询，聚焦适用性而非无依据的效率承诺。',
  },
  { id: 'travel' as const, name: '差旅办公 · 移动工作场景', audience: '经常出差的职场用户', scene: '差旅办公', date: '2026-10-20',
    title: '出差带电脑，先过一遍你的行程', opening: '用出门前准备行程的时刻，唤起差旅用户的具体需求。',
    lead: '通勤、会议、途中改材料，每一段行程都可以成为选购时的核对项目。',
    paragraphs: ['从出门前开始：要带哪些外设，需要处理什么文件，常用软件是否有明确的适用说明？先把这些问题写下来。', '再按具体机型核对资料。便携、供电和连接方式各有适用条件，不用一个笼统的“差旅神器”代替证据。', '把一次真实行程需要的材料带到门店，试过关键环节，再判断它能否进入自己的候选清单。'],
    short: '差旅选电脑，先过一遍行程：要接什么外设、要改什么材料、常用哪些软件。按具体机型核对资料，拿不准的环节可以带着文件到店体验。',
    structure: ['行程引出需求', '逐项核对具体资料', '把关键环节带到门店验证'], voice: '以行程为线索，克制描述，保留必要的验证边界。', cta: '把咨询转化为一次带着材料的体验邀请，不写具体门店或预约承诺。',
  },
];
const numbers = [
  [[3280,185,126,26],[1460,62,18,12],[null,35,null,8]],
  [[2140,104,76,17],[980,43,11,6],[null,22,null,5]],
  [[1760,86,54,13],[1230,51,15,9],[null,29,null,7]],
];
const platforms: DemoPlatform[] = ['xiaohongshu','wechat','moments'];
export const DEMO_CAMPAIGNS: DemoCampaign[] = stories.map((story, campaignIndex) => ({
  id: story.id, name: story.name, audience: story.audience, scene: story.scene, date: story.date,
  posts: platforms.map((platform, index) => {
    const [views, likes, saves, comments] = numbers[campaignIndex][index];
    return { id: `demo-history-${story.id}-${platform}`, campaignId: story.id, platform,
      title: platform === 'wechat' ? `${story.title}：一份场景选购笔记` : platform === 'moments' ? `${story.scene}，从实际需求开始` : story.title,
      lead: platform === 'moments' ? '' : story.lead, paragraphs: platform === 'moments' ? [story.short] : story.paragraphs,
      cta: '欢迎带着自己的使用需求，咨询或到店体验具体机型。', tags: platform === 'xiaohongshu' ? [`#${story.scene}`, '#选购笔记'] : [],
      images: platform === 'xiaohongshu' ? ['/planner-preview/scene-1.svg','/planner-preview/scene-2.svg','/planner-preview/scene-3.svg'] : platform === 'wechat' ? ['/planner-preview/scene-1.svg','/planner-preview/scene-2.svg'] : ['/planner-preview/scene-3.svg'],
      publishedAt: `${story.date}T10:00:00+08:00`, observedAt: '2026-10-21T18:00:00+08:00', metrics: {views, likes: likes!, saves, comments: comments!},
      lessons: { title: platform === 'moments' ? '用熟悉场景的一句话邀请开始，迅速聚焦一个选购任务。' : '以读者正在面对的选购问题为标题，给出清楚的阅读收益。', opening: story.opening, structure: platform === 'moments' ? ['一个具体需求','两三项核对建议','一次轻量邀请'] : story.structure, voice: story.voice, cta: story.cta },
    };
  }),
}));
export const DEMO_POSTS = DEMO_CAMPAIGNS.flatMap(campaign => campaign.posts);
export const CASE_STORAGE_KEY = 'hw-demo-history-cases-v1';
export const findDemoPost = (id: string) => DEMO_POSTS.find(post => post.id === id);
export const findDemoCampaign = (id: DemoContext) => DEMO_CAMPAIGNS.find(campaign => campaign.id === id)!;
export const metricText = (value: number | null) => value === null ? '—' : new Intl.NumberFormat('zh-CN').format(value);
export function demoDate(value: string, withTime = false) { return new Intl.DateTimeFormat('zh-CN', { year:'numeric', month:'2-digit', day:'2-digit', ...(withTime ? {hour:'2-digit',minute:'2-digit'} : {}), timeZone:'Asia/Shanghai' }).format(new Date(value)); }
