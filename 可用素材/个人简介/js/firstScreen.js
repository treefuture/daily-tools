let body = document.querySelector("body")

body.style.height = "100vh"
body.style.overflow = "hidden"

// 创建元素
let firstScreen = document.createElement("div")
let tempbox = document.createElement("div")
let tempbox2 = document.createElement("button")

// 给元素添加类名
firstScreen.classList.add("firstScreen")
tempbox.classList.add("content")
tempbox2.classList.add("content")

// 追加元素
// 获取body中的第一个子节点
let referenceNode = document.body.firstChild;

/**
 * 将 firstScreen 插入到 body 的第一个子节点之前
 * 如果 body 下没有任何子节点，appendChild 将会被使用
 */
if (referenceNode) {
  document.body.insertBefore(firstScreen, referenceNode);
} else {
  document.body.appendChild(firstScreen);
}

firstScreen.appendChild(tempbox)
firstScreen.appendChild(tempbox2)

// 按钮不可点击
tempbox2.disabled = true

// 按钮倒计时
let i = 5
let obj = setInterval(() => {
  i--
  tempbox2.innerText = `正在排队中 ${i}`
  if (i <= 0) {
    tempbox2.disabled = false
    tempbox2.innerText = "点击开启奇幻之旅..."
    clearInterval(obj)
  }
}, 1000)

// 给按钮添加点击事件
tempbox2.addEventListener("click", remove)
async function remove() {
  return await new Promise(res => {
    firstScreen.style.height = 0
    setTimeout(() => res(), 500)
  }).then(() => {
    document.body.removeChild(firstScreen)
    body.style.height = ""
    body.style.overflow = "scroll"
    musicStatus()
  })
}


