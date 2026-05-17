// 获取需要的元素
let dom = {
  mask: document.querySelector(".mask"),
  frameClose: document.querySelector(".frameClose"),
  img: document.querySelector(".pictureFrame img")
}

// 监听页面上所有的双击
document.addEventListener("dblclick", (event) => {
  if (event.target.src) {
    dom.mask.style.display = "flex"
    dom.img.src = event.target.src
  }
})

// 关闭窗口
dom.frameClose.addEventListener("click", () => {
  dom.mask.style.display = "none"
  dom.img.classList.remove("magnifier")
})

// 双击图片放大,还原
dom.img.addEventListener("dblclick", (event) => {
  if (dom.img.classList.contains('magnifier')) {
    dom.img.classList.remove("magnifier")
  } else {
    dom.img.classList.add("magnifier")
  }
})

// 鼠标移入移出控制图片放大、还原
// dom.img.addEventListener("mouseenter", (event) => {
//   if (dom.img.classList.contains('magnifier')) {
//     dom.img.classList.remove("magnifier")
//   } else {
//     dom.img.classList.add("magnifier")
//   }
// })
// dom.img.addEventListener("mouseleave", (event) => {
//   if (dom.img.classList.contains('magnifier')) {
//     dom.img.classList.remove("magnifier")
//   } else {
//     dom.img.classList.add("magnifier")
//   }
// })
