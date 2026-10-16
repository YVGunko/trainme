import { publishActivityParses } from '@/server/queue';
import { callRender } from '@/server/render';

export async function archivePeriodAndParse(start, end) {
  const result = await callRender('/archive/period', { start, end });
  const queue = await publishActivityParses(result);
  return { result, queue };
}
