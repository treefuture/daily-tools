export const requestTimeout = (
  url: string,
  options: object,
  timeout: number = 5000
) => {
  const controller = new AbortController();
  const signal = controller.signal;
  const fetchPromise = fetch(url, { ...options, signal });

  let timer: NodeJS.Timeout | null;

  const timePromise = new Promise((_, reject) => {
    timer = setTimeout(() => {
      controller.abort();
      reject('请求失败');
    }, timeout);
  });

  return Promise.race([fetchPromise, timePromise])
    .then((value) => {
      console.log(value);
    })
    .catch((error) => {
      console.log(error);
    })
    .finally(() => {
      if (timer !== null) {
        clearTimeout(timer);
      }
      timer = null;
    });
};
