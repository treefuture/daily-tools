/**
 * 设置页面逻辑：加载 / 保存配置
 */
'use strict';

const FIELDS = [
  'trailStyle',
  'trailColor',
  'arrowColor',
  'trailOpacity',
  'lineWidth',
  'showActionName',
  'minDragDistance'
];

const DEFAULTS = {
  trailStyle: 'both',
  trailColor: '#4488ff',
  arrowColor: '#4488ff',
  trailOpacity: 0.55,
  lineWidth: 3,
  showActionName: true,
  minDragDistance: 30
};

// DOM 引用缓存
const els = {};

function $(id) {
  return document.getElementById(id);
}

function init() {
  // 缓存 DOM
  for (const key of FIELDS) {
    els[key] = $(key);
  }
  els.saveBtn = $('saveBtn');
  els.resetBtn = $('resetBtn');
  els.toast = $('toast');
  els.opacityVal = $('opacityVal');

  // 加载设置
  chrome.storage.sync.get(DEFAULTS, applySettings);

  // 透明度滑块实时显示
  els.trailOpacity.addEventListener('input', () => {
    els.opacityVal.textContent = parseFloat(els.trailOpacity.value).toFixed(2);
  });

  // 保存
  els.saveBtn.addEventListener('click', saveSettings);
  // 重置
  els.resetBtn.addEventListener('click', resetSettings);
}

function applySettings(items) {
  for (const key of FIELDS) {
    const el = els[key];
    if (!el) continue;
    const val = items[key];
    if (el.type === 'checkbox') {
      el.checked = !!val;
    } else {
      el.value = val;
    }
  }
  if (items.trailOpacity != null) {
    els.opacityVal.textContent = parseFloat(items.trailOpacity).toFixed(2);
  }
}

function collectSettings() {
  const data = {};
  for (const key of FIELDS) {
    const el = els[key];
    if (!el) continue;
    if (el.type === 'checkbox') {
      data[key] = el.checked;
    } else if (el.type === 'number' || el.type === 'range') {
      data[key] = parseFloat(el.value);
    } else {
      data[key] = el.value;
    }
  }
  return data;
}

function saveSettings() {
  const data = collectSettings();
  chrome.storage.sync.set(data, () => {
    showToast('设置已保存 ✓');
  });
}

function resetSettings() {
  applySettings(DEFAULTS);
  saveSettings();
}

function showToast(msg) {
  els.toast.textContent = msg;
  els.toast.classList.add('show');
  clearTimeout(els.toast._timer);
  els.toast._timer = setTimeout(() => {
    els.toast.classList.remove('show');
  }, 2000);
}

document.addEventListener('DOMContentLoaded', init);
