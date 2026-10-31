const stepButtons = [...document.querySelectorAll('[data-step]')];
const demoTitle = document.querySelector('#demo-title');
const demoOverline = document.querySelector('#demo-overline');
const demoContent = document.querySelector('#demo-content');
const demoCounter = document.querySelector('#demo-counter');
const demoScene = document.querySelector('#demo-scene');
const nextButton = document.querySelector('#next-step');
const initialContent = demoContent.innerHTML;
let currentStep = 0;
let currentScenario = 'orders';

const scenarios = {
  orders: {
    label: '找订单',
    goal: '我想找抖音里的订单',
    title: '先找到「我的订单」',
    options: ['我的收藏', '我的订单', '观看历史'],
    instruction: '请点当前页面中间的「我的订单」。',
    finalTitle: '页面变了，再确认下一步',
    item: '我的订单',
    detail: '示例订单 · 页面内容仅作示意',
    nextInstruction: '如果来到商城页，可能还需再点一次「我的订单」，进入全部订单后选择商品。',
  },
  refund: {
    label: '申请退款',
    goal: '我想在抖音申请退款',
    title: '在订单详情里找申请入口',
    options: ['订单信息', '申请退款', '联系商家'],
    instruction: '先确认是你要处理的订单，再找「申请退款」。「退款/售后」可能只用于查看已有申请。',
    finalTitle: '看清申请，再自己决定',
    item: '申请退款',
    detail: '申请内容需由你检查和确认',
    nextInstruction: '根据实际页面填写申请。提交申请不等于退款到账。',
  },
  service: {
    label: '联系商家',
    goal: '我想在抖音联系商家客服',
    title: '在订单里找联系入口',
    options: ['订单信息', '联系商家', '售后记录'],
    instruction: '先确认对应商家，再找页面上的「联系商家」。',
    finalTitle: '找到入口，把问题问清楚',
    item: '联系商家',
    detail: '联系页面示意 · 不会实际发送消息',
    nextInstruction: '进入后，你可以自己输入想问的问题。',
  },
};

function showStep(index) {
  currentStep = index;
  const scenario = scenarios[currentScenario];
  demoScene.textContent = `${scenario.label} · 交互示意`;
  stepButtons.forEach((button, i) => {
    button.classList.toggle('active', i === index);
    button.setAttribute('aria-pressed', String(i === index));
  });
  demoCounter.textContent = `0${index + 1} / 03`;
  nextButton.innerHTML = index === 2 ? '重新体验 <span aria-hidden="true">↺</span>' : '看看下一步 <span aria-hidden="true">→</span>';
  if (index === 0) {
    demoOverline.textContent = '第一步 · 说出目标';
    demoTitle.textContent = '今天，想做点什么？';
    demoContent.innerHTML = initialContent;
    demoContent.querySelector('.example-input > span').textContent = scenario.goal;
    return;
  }
  if (index === 1) {
    demoOverline.textContent = '第二步 · 根据当前画面给出指导';
    demoTitle.textContent = scenario.title;
    demoContent.innerHTML = `<div class="demo-order-options">${scenario.options.map((label, i) => `<span class="${i === 1 ? 'demo-highlight' : ''}">${label}<span aria-hidden="true">${i === 1 ? '↖' : '›'}</span></span>`).join('')}</div><div class="demo-mini-guidance"><span aria-hidden="true">◖))</span>${scenario.instruction}</div>`;
    return;
  }
  demoOverline.textContent = '第三步 · 你来操作，小路继续指导';
  demoTitle.textContent = scenario.finalTitle;
  demoContent.innerHTML = `<div class="demo-order-card"><div class="demo-order-icon" aria-hidden="true">▤</div><div><strong>${scenario.item}</strong><small>${scenario.detail}</small></div></div><div class="demo-mini-guidance"><span aria-hidden="true">◖))</span>${scenario.nextInstruction}</div><p class="input-caption">可以重听、暂停，也可以反馈“没有找到”</p>`;
}

stepButtons.forEach(button => button.addEventListener('click', () => showStep(Number(button.dataset.step))));
nextButton.addEventListener('click', () => showStep((currentStep + 1) % 3));
document.querySelectorAll('[data-scenario]').forEach(link => {
  link.addEventListener('click', () => {
    currentScenario = link.dataset.scenario;
    showStep(0);
  });
});

const trialDialog = document.querySelector('#trial-dialog');
const privacyDialog = document.querySelector('#privacy-dialog');
document.querySelectorAll('[data-open-trial]').forEach(button => button.addEventListener('click', () => trialDialog.showModal()));
document.querySelectorAll('[data-open-privacy]').forEach(button => button.addEventListener('click', () => privacyDialog.showModal()));
document.querySelectorAll('dialog').forEach(dialog => {
  dialog.querySelectorAll('.dialog-close, .dialog-done').forEach(button => button.addEventListener('click', () => dialog.close()));
  dialog.addEventListener('click', event => {
    const box = dialog.getBoundingClientRect();
    if (event.target === dialog && (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom)) dialog.close();
  });
});
