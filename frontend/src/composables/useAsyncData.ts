import { ref, type Ref } from "vue";

/**
 * データ取得の loading / error / data パターンを統一する composable。
 *
 * 使い方:
 * ```ts
 * const { data, loading, error, execute } = useAsyncData(() => api.getSummary(30));
 * onMounted(execute);
 * ```
 */
export function useAsyncData<T>(
  fetcher: () => Promise<T>,
  options?: { immediate?: boolean },
) {
  const data = ref<T | null>(null) as Ref<T | null>;
  const loading = ref(false);
  const error = ref("");

  async function execute() {
    loading.value = true;
    error.value = "";
    try {
      data.value = await fetcher();
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : "データ取得失敗";
    } finally {
      loading.value = false;
    }
  }

  if (options?.immediate) {
    execute();
  }

  return { data, loading, error, execute };
}

/**
 * 複数の非同期データを並列取得する composable。
 *
 * 使い方:
 * ```ts
 * const { loading, error, execute } = useParallelData({
 *   summary: () => api.getSummary(30),
 *   news: () => api.getNews({ limit: 5 }),
 * });
 * onMounted(execute);
 * ```
 */
export function useParallelData<T extends Record<string, () => Promise<unknown>>>(
  fetchers: T,
) {
  type Results = { [K in keyof T]: Awaited<ReturnType<T[K]>> | null };
  const data = ref<Results>(
    Object.fromEntries(Object.keys(fetchers).map((k) => [k, null])) as Results,
  );
  const loading = ref(false);
  const error = ref("");

  async function execute() {
    loading.value = true;
    error.value = "";
    const keys = Object.keys(fetchers) as (keyof T)[];
    try {
      const results = await Promise.all(
        keys.map((k) => fetchers[k]().catch(() => null)),
      );
      const newData = {} as Results;
      for (let i = 0; i < keys.length; i++) {
        (newData as Record<string, unknown>)[keys[i] as string] = results[i];
      }
      data.value = newData;
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : "データ取得失敗";
    } finally {
      loading.value = false;
    }
  }

  return { data, loading, error, execute };
}
