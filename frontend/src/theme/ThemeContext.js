import { createContext } from 'react'

/**
 * 主题上下文：mode = 'light' | 'dark'
 * 提供 toggle / setMode；并自动把 data-theme 写到 <html> 上。
 */
export const ThemeContext = createContext({
  mode: 'light',
  toggle: () => {},
  setMode: () => {},
})

export default ThemeContext
