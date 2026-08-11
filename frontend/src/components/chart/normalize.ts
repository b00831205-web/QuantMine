import type { SeriesPoint } from '@/types/market';

/**
 * 把序列归一化到基期 100。
 *
 * 行为约定：
 * - 找到第一个 value !== 0 的点作为基准；
 * - 后续每点 = (value / baseValue) * 100；
 * - 若序列为空或全为 0，返回空数组；
 * - 不修改入参。
 *
 * 阶段 0 把函数体留给你实现，详见 TODO(USER_LEARNING)。
 *
 * 提示：
 * 1. 注意 SeriesPoint.value 可能是 0、可能是 undefined/NaN，请先做兜底；
 * 2. 使用 number | undefined 的安全运算；考虑是否需要先按 date 排序；
 * 3. 不要返回新的引用之外的副作用。
 */
export function normalizeToBase100(points: SeriesPoint[]): SeriesPoint[] {
  // TODO(USER_LEARNING):
  //   目标：把任意 SeriesPoint[] 归一化到首点 value=100；
  //   输入：可能为空、可能含 0；
  //   输出：新数组，保持 date 顺序，value 已归一化；
  //   提示：① 先过滤 NaN/undefined；② 找到首个非零点；③ 遍历计算比例；
    let baseValue: number | undefined
    for (const point of points){
      if (baseValue === undefined && point.value !==0 && Number.isFinite(point.value)){
        baseValue = point.value
      }
    }
    if (baseValue === undefined){
      return []
    }
    return points.filter((point)=> Number.isFinite(point.value)).map((point)=>({...point, value: (point.value/baseValue)*100}))
}
