/**
 * API 模块统一出口，按功能域拆分：
 *   dashboard / content / crm / knowledge / stocks / agents / settings
 */
export { default as api } from './client'
export { dashboardApi } from './dashboard'
export {
  hotTopicsApi,
  scriptsApi,
  videosApi,
  materialsApi,
  publishApi,
} from './content'
export { customersApi, followsApi, remindersApi } from './crm'
export { knowledgeApi } from './knowledge'
export { stocksApi } from './stocks'
export { agentsApi, workflowsApi } from './agents'
export { settingsApi, platformsApi } from './settings'
