let editingId = null;

function openModal(modalId, data = null) {
  const modal = document.getElementById(modalId);
  modal.querySelectorAll('input').forEach(i => (i.value = ''));
  if (data) {
    editingId = data.id;
    if (modalId === 'modal1') {
      document.getElementById('m1-title').value = data.title;
      document.getElementById('m1-listen').value = data.listen;
      document.getElementById('m1-target').value = data.target;
    } else {
      document.getElementById('m2-name').value = data.title;
      document.getElementById('m2-target').value = data.target;
    }
  } else {
    editingId = null;
  }
  modal.classList.remove('hidden');
}

function closeAll() {
  document.querySelectorAll('.modal').forEach(m => m.classList.add('hidden'));
  editingId = null;
}

document
  .querySelectorAll('.close-trigger')
  .forEach(b => (b.onclick = closeAll));
document.getElementById('btn-func1').onclick = () => openModal('modal1');
document.getElementById('btn-func2').onclick = () => openModal('modal2');

function saveData(type) {
  let item = { id: editingId || Date.now(), type: type };
  if (type === 'auto') {
    item.title = document.getElementById('m1-title').value;
    item.listen = document.getElementById('m1-listen').value.trim(); // 去空格
    item.target = document.getElementById('m1-target').value.trim();
  } else {
    item.title = document.getElementById('m2-name').value;
    item.target = document.getElementById('m2-target').value.trim();
  }
  chrome.storage.local.get({ items: [] }, res => {
    let items = editingId
      ? res.items.map(i => (i.id === editingId ? item : i))
      : [...res.items, item];
    chrome.storage.local.set({ items }, () => {
      render();
      closeAll();
    });
  });
}

document.getElementById('save-m1').onclick = () => saveData('auto');
document.getElementById('save-m2').onclick = () => saveData('manual');

function render() {
  chrome.storage.local.get({ items: [] }, res => {
    const container = document.getElementById('list-container');
    container.innerHTML = '';
    res.items.forEach(item => {
      const div = document.createElement('div');
      div.className = 'data-item';
      const isAuto = item.type === 'auto';

      div.innerHTML = `
                <div class="item-content">
                    <span class="tag ${isAuto ? 'tag-auto' : 'tag-manual'}">${isAuto ? '[自动监听]' : '[指定账号]'}</span>
                    <span class="item-title">${item.title}</span>
                </div>
                <div class="item-actions">
                    <button class="edit-btn">更改信息</button>
                    <button class="del-btn">删除</button>
                </div>
            `;

      div.querySelector('.del-btn').onclick = e => {
        e.stopPropagation();
        chrome.storage.local.set(
          { items: res.items.filter(i => i.id !== item.id) },
          render
        );
      };

      div.querySelector('.edit-btn').onclick = e => {
        e.stopPropagation();
        openModal(isAuto ? 'modal1' : 'modal2', item);
      };

      // 功能二：点击触发
      if (!isAuto) {
        const goBtn = document.createElement('button');
        goBtn.innerText = '执行功能';
        div.querySelector('.item-actions').appendChild(goBtn);

        const trigger = () => {
          // 发送 GO 消息给后台执行手动跳转逻辑
          chrome.runtime.sendMessage({ type: 'GO', url: item.target });
          // 跳转后应该关闭弹出层 ==> 设置延时只是为了更平滑的关闭
          setTimeout(() => {
            window.close();
          }, 200);
        };
        div.querySelector('.item-content').onclick = trigger;
        goBtn.onclick = e => {
          e.stopPropagation();
          trigger();
        };
      }

      container.appendChild(div);
    });
  });
}

document.addEventListener('DOMContentLoaded', render);
