import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { wechatOaPublicApi } from '../../api'
import './wechatOaMobile.css'

export default function WechatOaAbout() {
  const [profile, setProfile] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    wechatOaPublicApi.profile()
      .then(setProfile)
      .catch(err => setError(err?.error || err?.message || '加载失败'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return <div className="woa-page"><div className="woa-card">加载中…</div></div>
  }
  if (error) {
    return <div className="woa-page"><div className="woa-card woa-error">{error}</div></div>
  }
  if (!profile?.enabled) {
    return (
      <div className="woa-page">
        <div className="woa-card">
          <h1>暂未开放</h1>
          <p>对外服务页尚未启用，请稍后再试。</p>
        </div>
      </div>
    )
  }

  return (
    <div className="woa-page">
      <div className="woa-hero">
        <div className="woa-brand">{profile.brand_name}</div>
        <h1>{profile.intro_title}</h1>
      </div>
      <div className="woa-card">
        <p className="woa-text">{(profile.intro_text || '').split('\n').map((line, i) => (
          <span key={i}>{line}<br /></span>
        ))}</p>
        {(profile.contact_wechat || profile.contact_phone) && (
          <div className="woa-contact">
            {profile.contact_wechat && <p>微信：{profile.contact_wechat}</p>}
            {profile.contact_phone && <p>电话：{profile.contact_phone}</p>}
          </div>
        )}
        <Link className="woa-btn" to="/m/book">预约沟通</Link>
      </div>
    </div>
  )
}
