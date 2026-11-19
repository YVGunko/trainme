import { callRender } from '@/server/render';

// Ask the coach for the day's session. The Python side stores one recommendation
// per day and returns the stored one if it exists, so two runs a day do not
// produce two different plans that the athlete cannot tell apart.
export async function requestRecommendation(day) {
  return callRender('/recommend', { date: day });
}
