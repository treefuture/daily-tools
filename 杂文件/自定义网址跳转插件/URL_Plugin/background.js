/**
 * 核心执行函数：跳转并精准回滚
 * @param {number} tabId
 * @param {string} targetUrl 目标地址 (C)
 * @param {string} fallbackUrl 回退地址 (A 或 B)
 */
function executeSafeJump(tabId, targetUrl, fallbackUrl) {
  // 1. 执行跳转
  chrome.tabs.update(tabId, { url: targetUrl }, () => {
    // 2. 0.2秒后强制回滚到指定的 fallbackUrl
    setTimeout(() => {
      // 检查标签页是否还存在
      chrome.tabs.get(tabId, (tab) => {
        if (chrome.runtime.lastError || !tab) return;

        // 强制更新回之前的地址，而不是依赖浏览器的 goBack
        chrome.tabs.update(tabId, { url: fallbackUrl });
      });
    }, 200);
  });
}

// 监听自动跳转（功能一）
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  // status 为 loading 且有 URL 变更时触发
  if (changeInfo.url) {
    const currentUrl = changeInfo.url;

    chrome.storage.local.get({ items: [] }, (res) => {
      const match = res.items.find(
        (i) => i.type === "auto" && i.listen === currentUrl,
      );

      if (match) {
        // 【自动跳转逻辑】
        // 假设路径是 A -> B(当前match)，我们应该跳到 C，然后 0.2s 后回到 A
        // 我们需要获取 A 的地址。在 Chrome 中，我们可以通过 history 搜索上一条记录
        chrome.history.search({ text: "", maxResults: 2 }, (results) => {
          // results[0] 是当前 B，results[1] 通常是 A
          const fallback = results.length > 1 ? results[1].url : "about:newtab";

          // 为了防止 C 跳回 A 再次触发 B 的循环，我们在这里做个简单的标记
          if (!currentUrl.includes(match.target)) {
            executeSafeJump(tabId, match.target, fallback);
          }
        });
      }
    });
  }
});

// 监听手动执行（功能二）
chrome.runtime.onMessage.addListener((msg, sender) => {
  if (msg.type === "GO") {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (tabs[0]) {
        const tabId = tabs[0].id;
        const currentUrl = tabs[0].url; // 这就是执行时的页面 B

        // 【手动执行逻辑】从 B 跳到 C，0.2s 后回到 B
        executeSafeJump(tabId, msg.url, currentUrl);
      }
    });
  }
});
