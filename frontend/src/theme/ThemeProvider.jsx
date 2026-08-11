import { useEffect, useMemo, useState } from 'react'
import { ConfigProvider, theme as antdTheme } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { THEME } from '../config'
import ThemeContext from './ThemeContext'

const STORAGE_KEY = 'app-theme'

function getInitialMode() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved === 'light' || saved === 'dark') return saved
  } catch {
    /* ignore */
  }
  if (typeof window !== 'undefined' && window.matchMedia) {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  }
  return 'light'
}

const FONT_FAMILY =
  '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif'

/** 品牌色 / 尺寸：浅深共用。表面色仅在浅色强制，深色交给 darkAlgorithm。 */
const SHARED_TOKEN = {
  colorPrimary: THEME.colorPrimary,
  colorInfo: THEME.colorInfo,
  colorSuccess: THEME.colorSuccess,
  colorWarning: THEME.colorWarning,
  colorError: THEME.colorError,
  borderRadius: THEME.borderRadius,
  borderRadiusLG: THEME.borderRadiusLG,
  borderRadiusSM: 6,
  fontSize: THEME.fontSize,
  controlHeight: THEME.controlHeight,
  fontFamily: FONT_FAMILY,
  lineHeight: 1.6,
  wireframe: false,
}

const LIGHT_SURFACE = {
  colorText: THEME.colorText,
  colorTextSecondary: THEME.colorTextSecondary,
  colorTextTertiary: THEME.colorTextTertiary,
  colorBorder: THEME.colorBorder,
  colorBorderSecondary: THEME.colorBorderSecondary,
  colorBgLayout: THEME.colorBgLayout,
  colorBgContainer: THEME.colorBgContainer,
  colorBgElevated: THEME.colorBgContainer,
}

export default function ThemeProvider({ children }) {
  const [mode, setMode] = useState(getInitialMode)

  useEffect(() => {
    const root = document.documentElement
    root.setAttribute('data-theme', mode)
    try {
      localStorage.setItem(STORAGE_KEY, mode)
    } catch {
      /* ignore */
    }
  }, [mode])

  const value = useMemo(
    () => ({
      mode,
      toggle: () => setMode((m) => (m === 'dark' ? 'light' : 'dark')),
      setMode,
    }),
    [mode],
  )

  const themeTokens = useMemo(() => {
    const isDark = mode === 'dark'
    return {
      token: {
        ...SHARED_TOKEN,
        ...(isDark
          ? {
              // 略提亮主色，暗底上更清晰；其余表面色交给 darkAlgorithm
              colorPrimary: THEME.colorPrimaryLight || '#7d7dff',
            }
          : LIGHT_SURFACE),
      },
      algorithm: isDark ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
      components: {
        Button: {
          controlHeight: 34,
          controlHeightSM: 28,
          paddingContentHorizontal: 14,
          fontWeight: 500,
          primaryShadow: 'none',
          defaultShadow: 'none',
          borderRadius: 8,
        },
        Input: { controlHeight: 34, paddingBlock: 4, borderRadius: 8 },
        Select: { controlHeight: 34, borderRadius: 8 },
        Table: {
          headerBg: isDark ? '#16161f' : THEME.colorBgContainer,
          headerColor: isDark ? '#a4a4bc' : THEME.colorTextSecondary,
          headerSplitColor: isDark ? 'rgba(255,255,255,0.10)' : THEME.colorBorder,
          rowHoverBg: isDark ? 'rgba(123, 123, 255, 0.08)' : 'rgba(91, 91, 214, 0.04)',
          cellPaddingBlock: 12,
          cellPaddingInline: 16,
          borderColor: isDark ? 'rgba(255,255,255,0.07)' : THEME.colorBorderSecondary,
          headerBorderRadius: 0,
        },
        Card: { paddingLG: 20, headerHeight: 52, borderRadiusLG: 12 },
        Tag: {
          defaultBg: isDark ? '#1c1c27' : THEME.colorBgLayout,
          defaultColor: isDark ? '#a4a4bc' : THEME.colorTextSecondary,
          borderRadiusSM: 6,
        },
        Statistic: { titleFontSize: 12, contentFontSize: 28 },
        Alert: { borderRadiusLG: 8 },
        Pagination: { itemSize: 32, borderRadius: 6 },
        Menu: {
          itemHeight: 36,
          iconSize: 16,
          darkItemBg: 'transparent',
          darkSubMenuItemBg: 'transparent',
          darkItemSelectedBg: 'rgba(91, 91, 214, 0.2)',
          darkItemHoverBg: '#252542',
        },
        Tabs: {
          titleFontSize: 14,
          inkBarColor: isDark ? THEME.colorPrimaryLight : THEME.colorPrimary,
          itemSelectedColor: isDark ? THEME.colorPrimaryLight : THEME.colorPrimary,
          itemHoverColor: isDark ? '#e8e8f2' : THEME.colorText,
          itemColor: isDark ? '#a4a4bc' : THEME.colorTextSecondary,
          horizontalItemPadding: '10px 16px',
        },
        Form: { labelFontSize: 12, itemMarginBottom: 16 },
        Modal: { borderRadiusLG: 16 },
        Drawer: { paddingLG: 20 },
        Segmented: {
          itemSelectedColor: isDark ? THEME.colorPrimaryLight : THEME.colorPrimary,
          trackBg: isDark ? '#1c1c27' : THEME.colorBgLayout,
          trackPadding: 3,
        },
        Tooltip: { borderRadiusLG: 8 },
        Empty: { colorText: isDark ? '#a4a4bc' : THEME.colorTextSecondary },
      },
    }
  }, [mode])

  return (
    <ThemeContext.Provider value={value}>
      <ConfigProvider locale={zhCN} theme={themeTokens}>
        {children}
      </ConfigProvider>
    </ThemeContext.Provider>
  )
}
