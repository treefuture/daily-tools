/**
 * 后台 Service Worker
 * 接收 content_script 的手势消息，执行浏览器标签页操作
 */
'use strict';

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message.action) return;

  const tabId = sender.tab?.id;

  switch (message.action) {
    case 'NEW_TAB': {
      chrome.tabs.create({});
      break;
    }

    case 'CLOSE_TAB': {
      if (tabId) chrome.tabs.remove(tabId);
      break;
    }

    case 'REOPEN_TAB': {
      chrome.sessions.restore();
      break;
    }

    default:
      // 未知动作，忽略
      break;
  }
});

// 键盘快捷键命令（对 chrome:// 等受限页面兜底）
chrome.commands.onCommand.addListener(command => {
  switch (command) {
    case 'close-tab':
      chrome.tabs.query({ active: true, currentWindow: true }, tabs => {
        if (tabs[0]) chrome.tabs.remove(tabs[0].id);
      });
      break;
    case 'reopen-tab':
      chrome.sessions.restore();
      break;
  }
});

// 安装时打开设置页
chrome.runtime.onInstalled.addListener(details => {
  if (details.reason === 'install') {
    chrome.runtime.openOptionsPage();
  }
});
