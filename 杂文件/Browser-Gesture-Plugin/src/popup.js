/**
 * 弹出面板：提供快捷操作按钮
 */
'use strict';

document.getElementById('closeTab').addEventListener('click', () => {
  chrome.tabs.query({ active: true, currentWindow: true }, tabs => {
    if (tabs[0]) chrome.tabs.remove(tabs[0].id);
  });
});

document.getElementById('reopenTab').addEventListener('click', () => {
  chrome.sessions.restore();
});

document.getElementById('newTab').addEventListener('click', () => {
  chrome.tabs.create({});
});

document.getElementById('options').addEventListener('click', () => {
  chrome.runtime.openOptionsPage();
});
