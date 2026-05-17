
let point = document.querySelectorAll(".banner nav ul a")
let topnav = document.querySelector(".topnav")
let topnavbanner = document.querySelectorAll(".topnav nav ul a")
let backTop = document.querySelector(".backTop")
let sidebar = document.querySelector(".sidebar")

let info = document.querySelector("#info")
let game = document.querySelector("#game")
let film = document.querySelector("#film")

let arr = [info, game, film]

// 滚动条判断移动,未解决
for (let i = 0, j = point.length; i < j; i++) {
  point[i].addEventListener("click", () => {
    // window.scrollTo({ top: arr[i].getBoundingClientRect().top + (window.scrollY || document.documentElement.scrollTop) - topnav.clientHeight - 10, left: 0, behavior: "smooth" })
    window.scrollTo({ top: arr[i].getBoundingClientRect().top + (window.scrollY || document.documentElement.scrollTop) - 45 - 10, left: 0, behavior: "smooth" })
  })
}
for (let i = 0, j = topnavbanner.length; i < j; i++) {
  topnavbanner[i].addEventListener("click", () => {
    // window.scrollTo({ top: arr[i].getBoundingClientRect().top + (window.scrollY || document.documentElement.scrollTop) - topnav.clientHeight - 10, left: 0, behavior: "smooth" })

    window.scrollTo({ top: arr[i].getBoundingClientRect().top + (window.scrollY || document.documentElement.scrollTop) - 45 - 10, left: 0, behavior: "smooth" })
  })
}

document.addEventListener("scroll", scroll)
function scroll() {
  if ((document.documentElement.scrollTop || document.body.scrollTop) >= 120) {
    topnav.style.height = (document.documentElement.scrollTop || document.body.scrollTop) - 120 + "px"
  } else {
    topnav.style.height = 0
  }

  if ((document.documentElement.scrollTop || document.body.scrollTop) >= 300) {
    sidebar.style.left = "25px"
  } else {
    sidebar.style.left = "-300px"
  }

  if ((document.documentElement.scrollTop || document.body.scrollTop) >= 300) {
    backTop.style.right = "25px"
  } else {
    backTop.style.right = "-50px"
  }
}

// 回到顶部
backTop.addEventListener("click", () => {
  window.scrollTo({ top: 0, left: 0, behavior: "smooth" })
})

// 音乐开启和暂停
let musics = document.querySelectorAll(".musics")
musics[0].addEventListener("click", musicStatus)
musics[1].addEventListener("click", musicStatus)

// 判断音乐是否开启
function musicStatus() {
  let audio = document.querySelector("audio")
  if (audio.paused) {
    audio.play();
    musics[0].style.animationPlayState = ''
    musics[1].style.animationPlayState = ''
  } else {
    audio.pause();
    musics[0].style.animationPlayState = 'paused'
    musics[1].style.animationPlayState = 'paused'
  }
}
