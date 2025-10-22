import {
  SuperTask
} from "./SuperTask.js"

/**
 * 手写改造 PromisrAll 方法，该方法依赖 SuperTask 并发请求控制方法
 * @param {一个Promise数组，他其中的每一项也可以是一个数组。每一个Item也是数组的情况下请保证数组的第一项是需要执行的Promise函数，第二项是需要执行的回调函数} promiseArr 
 * @param {这个回调函数会在每个单独的请求执行完成时执行，如果您希望所有请求都执行完成后再执行特定的函数，那Promise自带方法可能更符合您的需求} callback 
 * @returns 返回一个promoise对象
 */
export const promiseAll = (promiseArr, callback) => {
  return new Promise((resolve, reject) => {
    const superTask = new SuperTask()
    if (!Array.isArray(promiseArr)) {
      throw new Error("参数只能为数组")
    }

    // 完成的 promise 数量
    let count = 0
    // 每个请求执行完成的返回值
    const taskValue = []
    for (let i = 0, len = promiseArr.length; i < len; i++) {
      const [promise, taskCallback] = promiseArr[i]
      superTask.add(promise).then(value => {
        if (value) {
          count++
          // 存储每个成功请求的返回值
          taskValue[i] = value
          // 请求完成的回调函数
          callback && callback(value)
          taskCallback && taskCallback(value)
        }

        if (count === len) {
          resolve(taskValue)
        }
      }).catch(err => reject(err))
    }
  })
}