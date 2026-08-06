import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { wechatOaPublicApi } from '../../api'
import './wechatOaMobile.css'

export default function WechatOaBook() {
  const [profile, setProfile] = useState(null)
  const [form, setForm] = useState({
    nickname: '',
    phone: '',
    wechat: '',
    preferred_time: '',
    remark: '',
  })
  const [submitting, setSubmitting] = useState(false)
  const [done, setDone] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    wechatOaPublicApi.profile()
      .then(setProfile)
      .catch(err => setError(err?.error || err?.message || '加载失败'))
  }, [])

  const onChange = (key) => (e) => setForm(prev => ({ ...prev, [key]: e.target.value }))

  const submit = (e) => {
    e.preventDefault()
    setError('')
    setSubmitting(true)
    wechatOaPublicApi.submitLead(form)
      .then(() => setDone(true))
      .catch(err => setError(err?.error || err?.message || '提交失败'))
      .finally(() => setSubmitting(false))
  }

  if (profile && !profile.enabled) {
    return (
      <div className="woa-page">
        <div className="woa-card">
          <h1>暂未开放</h1>
          <p>预约入口尚未启用。</p>
          <Link className="woa-link" to="/m/about">返回介绍</Link>
        </div>
      </div>
    )
  }

  if (done) {
    return (
      <div className="woa-page">
        <div className="woa-card">
          <h1>已收到</h1>
          <p>我们会尽快与你联系。你也可以先添加微信保持沟通。</p>
          {profile?.contact_wechat && <p className="woa-contact">微信：{profile.contact_wechat}</p>}
          <Link className="woa-btn" to="/m/about">返回介绍</Link>
        </div>
      </div>
    )
  }

  return (
    <div className="woa-page">
      <div className="woa-hero">
        <div className="woa-brand">{profile?.brand_name || '预约沟通'}</div>
        <h1>预约沟通</h1>
        <p className="woa-sub">{profile?.booking_hint}</p>
      </div>
      <form className="woa-card" onSubmit={submit}>
        <label className="woa-label">
          怎么称呼你 *
          <input className="woa-input" value={form.nickname} onChange={onChange('nickname')} required placeholder="如：张先生" />
        </label>
        <label className="woa-label">
          手机号
          <input className="woa-input" value={form.phone} onChange={onChange('phone')} placeholder="方便回电" inputMode="tel" />
        </label>
        <label className="woa-label">
          微信号
          <input className="woa-input" value={form.wechat} onChange={onChange('wechat')} placeholder="手机或微信号至少填一个" />
        </label>
        <label className="woa-label">
          方便联系的时间
          <input className="woa-input" value={form.preferred_time} onChange={onChange('preferred_time')} placeholder="如：工作日晚上" />
        </label>
        <label className="woa-label">
          想聊什么
          <textarea className="woa-input woa-textarea" value={form.remark} onChange={onChange('remark')} placeholder="可选" rows={3} />
        </label>
        {error && <div className="woa-error">{error}</div>}
        <button className="woa-btn" type="submit" disabled={submitting}>
          {submitting ? '提交中…' : '提交预约'}
        </button>
        <Link className="woa-link" to="/m/about">返回介绍</Link>
      </form>
    </div>
  )
}
