// 定义一个构造函数,用于处理并发问题
export class SuperTask {
  // 需要执行的任务
  tasks = []
  // 正在执行的任务数量
  runningCount = 0

  constructor(parallelCount = 2) {
    // 并发数量
    this.parallelCount = parallelCount
  }

  // 添加任务
  add(task) {
    return new Promise((resolve, reject) => {
      this.tasks.push({
        task,
        resolve,
        reject
      })
      this._run()
    })
  }

  // 执行任务
  _run() {
    while (this.runningCount < this.parallelCount && this.tasks.length > 0) {
      const {
        task,
        resolve,
        reject
      } = this.tasks.shift()

      task.then(value => {
        resolve(value)
      }, reject).finally(() => {
        this.runningCount--
      })
    }
  }
}