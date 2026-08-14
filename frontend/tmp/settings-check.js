// src/features/settings/SettingsModulePage.jsx
import { useEffect, useState } from "react";
import { useOutletContext, useParams } from "react-router-dom";
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Form,
  Input as Input2,
  Modal,
  Select as Select2,
  Space,
  Spin,
  Tag,
  message,
  Popconfirm,
  Table,
  InputNumber
} from "antd";
import {
  SaveOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  PlusOutlined,
  DeleteOutlined,
  ExperimentOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  EditOutlined
} from "@ant-design/icons";
import { settingsApi, platformsApi } from "../../api";

// src/features/settings/settingUtils.jsx
import { Input, Select, Switch } from "antd";
var { TextArea } = Input;
function flattenValues(settings) {
  const v = {};
  Object.entries(settings || {}).forEach(([cat, items]) => {
    ;
    (items || []).forEach((item) => {
      v[`${item.category}.${item.key}`] = item.value;
    });
  });
  return v;
}
function groupValues(values) {
  const grouped = {};
  Object.entries(values).forEach(([key, val]) => {
    const dot = key.indexOf(".");
    if (dot < 0) return;
    const cat = key.slice(0, dot);
    const k = key.slice(dot + 1);
    if (!grouped[cat]) grouped[cat] = {};
    grouped[cat][k] = val;
  });
  return grouped;
}
function renderSettingField(item, values, setValues) {
  const fieldKey = `${item.category}.${item.key}`;
  const val = values[fieldKey] ?? item.value;
  const onChange = (v) => setValues((prev) => ({ ...prev, [fieldKey]: v }));
  if (item.key === "enabled" && item.field_type === "select") {
    const checked = String(val) === "true";
    return /* @__PURE__ */ React.createElement(
      Switch,
      {
        checked,
        checkedChildren: "\u542F\u7528",
        unCheckedChildren: "\u5173\u95ED",
        onChange: (c) => onChange(c ? "true" : "false")
      }
    );
  }
  if (item.field_type === "password") {
    return /* @__PURE__ */ React.createElement(Input.Password, { value: val, onChange: (e) => onChange(e.target.value), placeholder: item.description });
  }
  if (item.field_type === "textarea") {
    return /* @__PURE__ */ React.createElement(TextArea, { value: val, onChange: (e) => onChange(e.target.value), rows: 4, placeholder: item.description });
  }
  if (item.field_type === "select" && item.options) {
    const opts = typeof item.options === "string" ? JSON.parse(item.options) : item.options;
    return /* @__PURE__ */ React.createElement(
      Select,
      {
        value: val,
        onChange,
        style: { width: "100%" },
        options: (opts || []).map((o) => ({ label: String(o), value: String(o) }))
      }
    );
  }
  return /* @__PURE__ */ React.createElement(Input, { value: val, onChange: (e) => onChange(e.target.value), placeholder: item.description });
}

// src/features/settings/SettingsModulePage.jsx
var COLOR_OPTIONS = [
  { value: "green", label: "\u7EFF" },
  { value: "black", label: "\u9ED1" },
  { value: "red", label: "\u7EA2" },
  { value: "blue", label: "\u84DD" },
  { value: "orange", label: "\u6A59" },
  { value: "purple", label: "\u7D2B" },
  { value: "cyan", label: "\u9752" }
];
var CATEGORY_TITLES = {
  ai: "\u6A21\u578B\u4E0E API",
  tts: "\u914D\u97F3 (TTS)",
  video: "\u89C6\u9891\u5236\u4F5C",
  system: "\u5185\u5BB9\u4E0E\u91C7\u96C6\u7B56\u7565",
  notify: "\u5FAE\u4FE1\u63A8\u9001",
  wechat_oa: "\u5FAE\u4FE1\u670D\u52A1\u53F7",
  web: "\u8054\u7F51\u641C\u7D22"
};
function SettingsModulePage() {
  const { moduleKey } = useParams();
  const { modules } = useOutletContext() || {};
  const mod = (modules || []).find((m) => m.path === moduleKey);
  const [settings, setSettings] = useState({});
  const [readiness, setReadiness] = useState({});
  const [values, setValues] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const load = () => {
    setLoading(true);
    Promise.all([settingsApi.get(), settingsApi.check()]).then(([s, r]) => {
      setSettings(s);
      setReadiness(r);
      setValues(flattenValues(s));
    }).finally(() => setLoading(false));
  };
  useEffect(() => {
    load();
  }, [moduleKey]);
  if (!mod) {
    return /* @__PURE__ */ React.createElement(Alert, { type: "warning", message: "\u672A\u77E5\u914D\u7F6E\u6A21\u5757" });
  }
  if (mod.type === "collector_platforms" || mod.type === "publish_platforms" || mod.type === "commercial_providers") {
    return /* @__PURE__ */ React.createElement(PlatformsPage, { mod });
  }
  if (mod.type === "notify_channels") {
    return /* @__PURE__ */ React.createElement(NotifyChannelsPage, { mod });
  }
  if (mod.type === "ai_providers") {
    return /* @__PURE__ */ React.createElement(AiProvidersPage, { mod });
  }
  if (mod.type === "wechat_oa") {
    return /* @__PURE__ */ React.createElement(WechatOaSettingsPage, { mod });
  }
  if (mod.type === "scheduled_tasks") {
    return /* @__PURE__ */ React.createElement(ScheduledTasksPage, null);
  }
  const handleSave = () => {
    setSaving(true);
    const cats = mod.categories || [];
    const all = groupValues(values);
    const payload = {};
    cats.forEach((c) => {
      if (all[c]) payload[c] = all[c];
    });
    settingsApi.update(payload).then(() => {
      message.success("\u5DF2\u4FDD\u5B58");
      load();
    }).catch(() => message.error("\u4FDD\u5B58\u5931\u8D25")).finally(() => setSaving(false));
  };
  if (loading) {
    return /* @__PURE__ */ React.createElement("div", { style: { textAlign: "center", padding: 60 } }, /* @__PURE__ */ React.createElement(Spin, null));
  }
  return /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16, gap: 12, flexWrap: "wrap" } }, /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("div", { className: "page-title" }, mod.label), /* @__PURE__ */ React.createElement("div", { className: "page-desc", style: { marginBottom: 0 } }, mod.desc)), /* @__PURE__ */ React.createElement(Button, { type: "primary", icon: /* @__PURE__ */ React.createElement(SaveOutlined, null), loading: saving, onClick: handleSave }, "\u4FDD\u5B58")), (mod.categories || []).map((cat) => {
    const items = settings[cat];
    if (!items?.length) return null;
    const ready = readiness[cat] || readiness[mod.key];
    return /* @__PURE__ */ React.createElement(
      Card,
      {
        key: cat,
        style: { marginBottom: 16 },
        title: CATEGORY_TITLES[cat] || cat,
        extra: ready && (ready.ready ? /* @__PURE__ */ React.createElement(Tag, { icon: /* @__PURE__ */ React.createElement(CheckCircleOutlined, null), color: "success" }, "\u5C31\u7EEA") : /* @__PURE__ */ React.createElement(Tag, { icon: /* @__PURE__ */ React.createElement(ExclamationCircleOutlined, null), color: "warning" }, "\u5F85\u914D\u7F6E"))
      },
      /* @__PURE__ */ React.createElement(Form, { layout: "vertical" }, (items || []).filter((item) => !(mod.exclude_keys || []).includes(item.key)).map((item) => /* @__PURE__ */ React.createElement(Form.Item, { key: item.key, label: item.label, extra: item.description }, renderSettingField(item, values, setValues))))
    );
  }));
}
function NotifyChannelsPage({ mod }) {
  const [settings, setSettings] = useState({});
  const [readiness, setReadiness] = useState({});
  const [values, setValues] = useState({});
  const [loading, setLoading] = useState(true);
  const [savingKey, setSavingKey] = useState(null);
  const [testingKey, setTestingKey] = useState(null);
  const [activeKey, setActiveKey] = useState(null);
  const channels = mod.platforms || [];
  const load = () => {
    setLoading(true);
    Promise.all([settingsApi.get(), settingsApi.check()]).then(([s, r]) => {
      setSettings(s);
      setReadiness(r);
      setValues(flattenValues(s));
      setActiveKey((prev) => {
        if (prev && channels.some((p) => p.key === prev)) return prev;
        return channels[0]?.key || null;
      });
    }).finally(() => setLoading(false));
  };
  useEffect(() => {
    load();
  }, [mod.key, channels.map((p) => p.key).join(",")]);
  const saveChannel = (channel) => {
    const cat = channel.category;
    setSavingKey(channel.key);
    const all = groupValues(values);
    const payload = { [cat]: all[cat] || {} };
    if (channel.key !== "rules") {
      const enabling = String(payload[cat]?.enabled || "").toLowerCase() === "true";
      if (enabling) {
        channels.forEach((c) => {
          if (c.key === "rules" || c.key === channel.key) return;
          payload[c.category] = {
            ...all[c.category] || {},
            enabled: "false"
          };
        });
      }
    }
    settingsApi.update(payload).then(() => {
      message.success(`${channel.label} \u5DF2\u4FDD\u5B58`);
      load();
    }).catch(() => message.error("\u4FDD\u5B58\u5931\u8D25")).finally(() => setSavingKey(null));
  };
  const handleTest = (channel) => {
    if (channel.key === "rules") return;
    setTestingKey(channel.key);
    const cat = channel.category;
    const all = groupValues(values);
    const payload = { [cat]: all[cat] || {} };
    settingsApi.update(payload).then(() => settingsApi.testNotify({ channel: channel.key })).then((res) => {
      message.success(res?.message || "\u6D4B\u8BD5\u6D88\u606F\u5DF2\u53D1\u9001");
      load();
    }).catch((err) => message.error(err?.error || err?.message || "\u6D4B\u8BD5\u5931\u8D25")).finally(() => setTestingKey(null));
  };
  if (loading) {
    return /* @__PURE__ */ React.createElement("div", { style: { textAlign: "center", padding: 60 } }, /* @__PURE__ */ React.createElement(Spin, null));
  }
  const moduleReady = readiness[mod.key];
  const current = channels.find((p) => p.key === activeKey) || channels[0];
  const isRules = current?.key === "rules";
  const statusTag = (channel) => {
    if (channel.key === "rules") {
      return /* @__PURE__ */ React.createElement(Tag, { color: "purple" }, "\u4E8B\u4EF6\u5F00\u5173");
    }
    const ready = readiness[channel.category];
    if (ready?.enabled && ready?.ready) return /* @__PURE__ */ React.createElement(Tag, { color: "success" }, "\u5DF2\u542F\u7528");
    if (ready?.enabled) return /* @__PURE__ */ React.createElement(Tag, { color: "warning" }, "\u5F85\u914D\u51ED\u8BC1");
    return /* @__PURE__ */ React.createElement(Tag, { color: "default" }, "\u672A\u542F\u7528");
  };
  return /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("div", { style: { marginBottom: 16 } }, /* @__PURE__ */ React.createElement("div", { className: "page-title" }, mod.label), /* @__PURE__ */ React.createElement("div", { className: "page-desc", style: { marginBottom: 0 } }, mod.desc), /* @__PURE__ */ React.createElement(
    Alert,
    {
      style: { marginTop: 12 },
      type: "info",
      showIcon: true,
      message: moduleReady?.message || "\u63A8\u8350\u542F\u7528\u4F01\u4E1A\u5FAE\u4FE1\u7FA4\u673A\u5668\u4EBA\uFF08\u514D\u8D39\uFF09",
      description: "\u4E0A\u65B9\u9009\u62E9\u63A8\u9001\u6E20\u9053\uFF1B\u542F\u7528\u4E00\u4E2A\u6E20\u9053\u5373\u53EF\u3002\u4F01\u5FAE\uFF1A\u5EFA\u7FA4 \u2192 \u6DFB\u52A0\u7FA4\u673A\u5668\u4EBA \u2192 \u7C98\u8D34 Webhook \u2192 \u4FDD\u5B58\u5E76\u53D1\u9001\u6D4B\u8BD5\u3002"
    }
  )), /* @__PURE__ */ React.createElement("div", { className: "settings-plat-switch" }, channels.map((p) => {
    const selected = current?.key === p.key;
    const ready = readiness[p.category];
    const on = !!(ready?.enabled && ready?.ready);
    return /* @__PURE__ */ React.createElement(
      "button",
      {
        key: p.key,
        type: "button",
        className: `settings-plat-pill${selected ? " active" : ""}`,
        onClick: () => setActiveKey(p.key)
      },
      /* @__PURE__ */ React.createElement("span", { className: `dot ${on ? "on" : "off"}` }),
      p.label,
      p.recommended ? " \xB7 \u63A8\u8350" : ""
    );
  })), current && /* @__PURE__ */ React.createElement("div", { className: "settings-plat-meta" }, /* @__PURE__ */ React.createElement("span", { className: "meta-text" }, current.desc), statusTag(current)), /* @__PURE__ */ React.createElement("div", null, current && /* @__PURE__ */ React.createElement(
    Card,
    {
      title: /* @__PURE__ */ React.createElement(Space, null, current.label, /* @__PURE__ */ React.createElement(Tag, null, "\u63A8\u9001"), current.recommended && /* @__PURE__ */ React.createElement(Tag, { color: "green" }, "\u63A8\u8350")),
      extra: /* @__PURE__ */ React.createElement(Space, null, !isRules && /* @__PURE__ */ React.createElement(
        Button,
        {
          icon: /* @__PURE__ */ React.createElement(ExperimentOutlined, null),
          loading: testingKey === current.key,
          onClick: () => handleTest(current)
        },
        "\u53D1\u9001\u6D4B\u8BD5"
      ), /* @__PURE__ */ React.createElement(
        Button,
        {
          type: "primary",
          icon: /* @__PURE__ */ React.createElement(SaveOutlined, null),
          loading: savingKey === current.key,
          onClick: () => saveChannel(current)
        },
        "\u4FDD\u5B58"
      ))
    },
    !isRules && current.key === "wecom" && /* @__PURE__ */ React.createElement(
      Alert,
      {
        style: { marginBottom: 16 },
        type: "success",
        showIcon: true,
        message: "\u4F01\u4E1A\u5FAE\u4FE1\u514D\u8D39\uFF0C\u4E0D\u7528 PushPlus \u5B9E\u540D\u4ED8\u8D39",
        description: "\u624B\u673A\u4F01\u5FAE\u5EFA\u4E00\u4E2A\u53EA\u6709\u81EA\u5DF1\u7684\u7FA4 \u2192 \u7FA4\u673A\u5668\u4EBA \u2192 \u590D\u5236 Webhook \u586B\u5230\u4E0B\u65B9\u5E76\u542F\u7528\u3002"
      }
    ),
    /* @__PURE__ */ React.createElement(Form, { layout: "vertical" }, (settings[current.category] || []).filter((item) => !isRules || ["on_stock_alert", "on_screening_done"].includes(item.key)).map((item) => /* @__PURE__ */ React.createElement(Form.Item, { key: item.key, label: item.label, extra: item.description }, renderSettingField(item, values, setValues))), !(settings[current.category] || []).length && /* @__PURE__ */ React.createElement(Alert, { type: "warning", message: "\u8BE5\u6E20\u9053\u5C1A\u672A\u521D\u59CB\u5316\u914D\u7F6E\u9879\uFF0C\u8BF7\u5237\u65B0\u9875\u9762\u6216\u91CD\u542F\u540E\u7AEF\u3002" }))
  )));
}
function WechatOaSettingsPage({ mod }) {
  const [settings, setSettings] = useState({});
  const [values, setValues] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [links, setLinks] = useState(null);
  const load = () => {
    setLoading(true);
    Promise.all([settingsApi.get(), settingsApi.wechatOaMenuLinks()]).then(([s, l]) => {
      setSettings(s);
      setValues(flattenValues(s));
      setLinks(l);
    }).catch(() => message.error("\u52A0\u8F7D\u5931\u8D25")).finally(() => setLoading(false));
  };
  useEffect(() => {
    load();
  }, [mod.key]);
  const handleSave = () => {
    setSaving(true);
    const payload = groupValues(values);
    settingsApi.update(payload).then(() => {
      message.success("\u670D\u52A1\u53F7\u914D\u7F6E\u5DF2\u4FDD\u5B58");
      return settingsApi.wechatOaMenuLinks();
    }).then((l) => setLinks(l)).catch(() => message.error("\u4FDD\u5B58\u5931\u8D25")).finally(() => setSaving(false));
  };
  const copyText = (text) => {
    if (!text) {
      message.warning("\u8BF7\u5148\u586B\u5199\u5E76\u4FDD\u5B58\u300C\u5BF9\u5916\u8BBF\u95EE\u5730\u5740\u300D");
      return;
    }
    navigator.clipboard?.writeText(text).then(() => message.success("\u5DF2\u590D\u5236")).catch(() => message.info(text));
  };
  if (loading) {
    return /* @__PURE__ */ React.createElement("div", { style: { textAlign: "center", padding: 60 } }, /* @__PURE__ */ React.createElement(Spin, null));
  }
  const items = settings.wechat_oa || [];
  return /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("div", { className: "page-title" }, mod.label), /* @__PURE__ */ React.createElement("div", { className: "page-desc" }, mod.desc), /* @__PURE__ */ React.createElement(
    Alert,
    {
      style: { marginBottom: 16 },
      type: "info",
      showIcon: true,
      message: "\u9636\u6BB5\u2460\uFF1A\u670D\u52A1\u53F7\u83DC\u5355 + \u5BA2\u6237\u9875\uFF08\u6539\u52A8\u6700\u5C0F\uFF09",
      description: /* @__PURE__ */ React.createElement("ol", { style: { margin: "8px 0 0", paddingLeft: 18 } }, /* @__PURE__ */ React.createElement("li", null, "\u5728\u5FAE\u4FE1\u516C\u4F17\u5E73\u53F0\u6CE8\u518C\u5E76\u8BA4\u8BC1\u300C\u670D\u52A1\u53F7\u300D"), /* @__PURE__ */ React.createElement("li", null, "\u672C\u9875\u586B\u5199\u54C1\u724C\u6587\u6848\uFF0C\u6253\u5F00\u300C\u542F\u7528\u300D\uFF0C\u586B\u5BA2\u6237\u80FD\u6253\u5F00\u7684\u300C\u5BF9\u5916\u8BBF\u95EE\u5730\u5740\u300D"), /* @__PURE__ */ React.createElement("li", null, "\u516C\u4F17\u5E73\u53F0 \u2192 \u81EA\u5B9A\u4E49\u83DC\u5355\uFF1A\u4ECB\u7ECD\u9875 / \u9884\u7EA6\u6C9F\u901A\uFF0C\u7C98\u8D34\u4E0B\u65B9\u94FE\u63A5"), /* @__PURE__ */ React.createElement("li", null, "\u5BA2\u6237\u63D0\u4EA4\u9884\u7EA6\u540E\uFF0C\u4F1A\u51FA\u73B0\u5728\u300C\u7EBF\u7D22\u6C60\u300D\uFF0C\u5E76\u5C3D\u91CF\u8D70\u6D88\u606F\u63A8\u9001\u901A\u77E5\u4F60\uFF1B\u8F6C\u5BA2\u6237\u540E\u518D\u8FDB\u5BA2\u6237\u5217\u8868"))
    }
  ), /* @__PURE__ */ React.createElement(Card, { title: "\u83DC\u5355\u94FE\u63A5\uFF08\u590D\u5236\u5230\u516C\u4F17\u5E73\u53F0\uFF09", style: { marginBottom: 16 } }, /* @__PURE__ */ React.createElement("p", { style: { color: "#666", marginBottom: 12 } }, links?.hint), /* @__PURE__ */ React.createElement(Space, { direction: "vertical", style: { width: "100%" }, size: "middle" }, /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("div", { style: { marginBottom: 6 } }, "\u4ECB\u7ECD\u9875"), /* @__PURE__ */ React.createElement(Space.Compact, { style: { width: "100%" } }, /* @__PURE__ */ React.createElement(Input2, { readOnly: true, value: links?.about_url || `\uFF08\u4FDD\u5B58\u5BF9\u5916\u5730\u5740\u540E\u751F\u6210\uFF09\u2026${links?.about_path || "/m/about"}` }), /* @__PURE__ */ React.createElement(Button, { onClick: () => copyText(links?.about_url) }, "\u590D\u5236"))), /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("div", { style: { marginBottom: 6 } }, "\u9884\u7EA6\u6C9F\u901A"), /* @__PURE__ */ React.createElement(Space.Compact, { style: { width: "100%" } }, /* @__PURE__ */ React.createElement(Input2, { readOnly: true, value: links?.book_url || `\uFF08\u4FDD\u5B58\u5BF9\u5916\u5730\u5740\u540E\u751F\u6210\uFF09\u2026${links?.book_path || "/m/book"}` }), /* @__PURE__ */ React.createElement(Button, { onClick: () => copyText(links?.book_url) }, "\u590D\u5236"))), /* @__PURE__ */ React.createElement(Space, { wrap: true }, /* @__PURE__ */ React.createElement(Button, { href: links?.about_path || "/m/about", target: "_blank" }, "\u672C\u673A\u9884\u89C8\u4ECB\u7ECD\u9875"), /* @__PURE__ */ React.createElement(Button, { href: links?.book_path || "/m/book", target: "_blank" }, "\u672C\u673A\u9884\u89C8\u9884\u7EA6\u9875")))), /* @__PURE__ */ React.createElement(
    Card,
    {
      title: "\u5BF9\u5916\u5185\u5BB9\u4E0E\u5F00\u5173",
      extra: /* @__PURE__ */ React.createElement(Button, { type: "primary", icon: /* @__PURE__ */ React.createElement(SaveOutlined, null), loading: saving, onClick: handleSave }, "\u4FDD\u5B58")
    },
    /* @__PURE__ */ React.createElement(Form, { layout: "vertical" }, items.map((item) => /* @__PURE__ */ React.createElement(Form.Item, { key: item.key, label: item.label, extra: item.description }, renderSettingField(item, values, setValues))), !items.length && /* @__PURE__ */ React.createElement(Alert, { type: "warning", message: "\u914D\u7F6E\u9879\u672A\u521D\u59CB\u5316\uFF0C\u8BF7\u91CD\u542F\u540E\u7AEF\u540E\u518D\u6253\u5F00\u672C\u9875\u3002" }))
  ));
}
function AiProvidersPage({ mod }) {
  const { reloadModules } = useOutletContext() || {};
  const [settings, setSettings] = useState({});
  const [readiness, setReadiness] = useState({});
  const [values, setValues] = useState({});
  const [loading, setLoading] = useState(true);
  const [savingKey, setSavingKey] = useState(null);
  const [testingKey, setTestingKey] = useState(null);
  const [activeKey, setActiveKey] = useState(null);
  const [addOpen, setAddOpen] = useState(false);
  const [adding, setAdding] = useState(false);
  const [form] = Form.useForm();
  const cards = mod.platforms || [];
  const load = () => {
    setLoading(true);
    Promise.all([settingsApi.get(), settingsApi.check()]).then(([s, r]) => {
      setSettings(s);
      setReadiness(r);
      setValues(flattenValues(s));
      setActiveKey((prev) => {
        if (prev && cards.some((p) => p.key === prev)) return prev;
        const enabled = cards.find((p) => p.key !== "common" && r?.[p.category]?.enabled);
        return enabled?.key || cards[0]?.key || null;
      });
    }).finally(() => setLoading(false));
  };
  useEffect(() => {
    load();
  }, [mod.key, cards.map((p) => p.key).join(",")]);
  const saveCard = (card) => {
    const cat = card.category;
    setSavingKey(card.key);
    const all = groupValues(values);
    const payload = { [cat]: all[cat] || {} };
    if (card.key !== "common") {
      const enabling = String(payload[cat]?.enabled || "").toLowerCase() === "true";
      if (enabling) {
        cards.forEach((c) => {
          if (c.key === "common" || c.key === card.key) return;
          payload[c.category] = {
            ...all[c.category] || {},
            enabled: "false"
          };
        });
      }
    }
    settingsApi.update(payload).then(() => {
      message.success(`${card.label} \u5DF2\u4FDD\u5B58`);
      load();
    }).catch(() => message.error("\u4FDD\u5B58\u5931\u8D25")).finally(() => setSavingKey(null));
  };
  const handleTest = (card) => {
    if (card.key === "common") return;
    setTestingKey(card.key);
    const cat = card.category;
    const all = groupValues(values);
    settingsApi.update({ [cat]: all[cat] || {} }).then(() => settingsApi.testAi({ provider: card.key })).then((res) => {
      message.success(`${res?.message || "\u8FDE\u901A\u6210\u529F"}\uFF08${res?.model || card.key}\uFF09`);
      load();
    }).catch((err) => message.error(err?.error || err?.message || "\u6D4B\u8BD5\u5931\u8D25")).finally(() => setTestingKey(null));
  };
  const handleAdd = () => {
    form.validateFields().then((vals) => {
      setAdding(true);
      settingsApi.createAiProvider({
        key: vals.key,
        label: vals.label,
        desc: vals.desc || "",
        color: vals.color || "blue",
        default_base_url: vals.default_base_url || "",
        default_model: vals.default_model || "",
        model_hint: vals.model_hint || ""
      }).then((res) => {
        message.success(res.message || "\u5382\u5546\u5DF2\u6DFB\u52A0");
        setAddOpen(false);
        form.resetFields();
        return reloadModules?.();
      }).then(() => {
        setActiveKey(vals.key);
        load();
      }).catch((err) => message.error(err?.error || "\u6DFB\u52A0\u5931\u8D25")).finally(() => setAdding(false));
    });
  };
  const handleDelete = (card) => {
    settingsApi.deleteAiProvider(card.key).then((res) => {
      message.success(res.message || "\u5DF2\u5220\u9664");
      return reloadModules?.();
    }).then(() => {
      setActiveKey(null);
      load();
    }).catch((err) => message.error(err?.error || "\u5220\u9664\u5931\u8D25"));
  };
  if (loading) {
    return /* @__PURE__ */ React.createElement("div", { style: { textAlign: "center", padding: 60 } }, /* @__PURE__ */ React.createElement(Spin, null));
  }
  const moduleReady = readiness[mod.key];
  const current = cards.find((p) => p.key === activeKey) || cards[0];
  const isCommon = current?.key === "common";
  const visibleFields = (card) => {
    const items = settings[card.category] || [];
    if (card.key === "common") return items;
    return items.filter((item) => !["auth_type", "username", "password"].includes(item.key));
  };
  const statusTag = (card) => {
    if (card.key === "common") return /* @__PURE__ */ React.createElement(Tag, { color: "purple" }, "\u5171\u7528");
    const ready = readiness[card.category];
    if (ready?.enabled && ready?.ready) return /* @__PURE__ */ React.createElement(Tag, { color: "success" }, "\u4F7F\u7528\u4E2D");
    if (ready?.enabled) return /* @__PURE__ */ React.createElement(Tag, { color: "warning" }, "\u5F85\u914D\u9F50");
    if (ready?.message?.includes("\u5DF2\u586B")) return /* @__PURE__ */ React.createElement(Tag, { color: "blue" }, "\u5DF2\u914D\u7F6E");
    return /* @__PURE__ */ React.createElement(Tag, { color: "default" }, "\u672A\u542F\u7528");
  };
  return /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("div", { style: { marginBottom: 16, display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, flexWrap: "wrap" } }, /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("div", { className: "page-title" }, mod.label), /* @__PURE__ */ React.createElement("div", { className: "page-desc", style: { marginBottom: 0 } }, mod.desc), /* @__PURE__ */ React.createElement(
    Alert,
    {
      style: { marginTop: 12 },
      type: "info",
      showIcon: true,
      message: moduleReady?.message || "\u9009\u62E9\u4E00\u5BB6\u5927\u6A21\u578B\u5E76\u542F\u7528",
      description: "\u586B\u5199 API Key \u540E\u542F\u7528\u5373\u53EF\u3002ChatGPT/GPT \u8BF7\u9009\u300COpenAI / ChatGPT\u300D\uFF0C\u4F7F\u7528 platform.openai.com \u7684 sk- Key\u3002"
    }
  )), /* @__PURE__ */ React.createElement(
    Button,
    {
      type: "primary",
      icon: /* @__PURE__ */ React.createElement(PlusOutlined, null),
      onClick: () => {
        form.resetFields();
        form.setFieldsValue({ color: "blue" });
        setAddOpen(true);
      }
    },
    "\u6DFB\u52A0\u6A21\u578B"
  )), /* @__PURE__ */ React.createElement("div", { className: "settings-plat-switch" }, cards.map((p) => {
    const selected = current?.key === p.key;
    const ready = readiness[p.category];
    const on = !!(ready?.enabled && ready?.ready);
    return /* @__PURE__ */ React.createElement(
      "button",
      {
        key: p.key,
        type: "button",
        className: `settings-plat-pill${selected ? " active" : ""}`,
        onClick: () => setActiveKey(p.key)
      },
      /* @__PURE__ */ React.createElement("span", { className: `dot ${on ? "on" : "off"}` }),
      p.label,
      p.recommended ? " \xB7 \u63A8\u8350" : ""
    );
  })), current && /* @__PURE__ */ React.createElement("div", { className: "settings-plat-meta" }, /* @__PURE__ */ React.createElement("span", { className: "meta-text" }, current.desc), statusTag(current)), /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("div", { style: { minWidth: 0 } }, current && /* @__PURE__ */ React.createElement(
    Card,
    {
      title: /* @__PURE__ */ React.createElement(Space, null, current.label, /* @__PURE__ */ React.createElement(Tag, null, "\u5927\u6A21\u578B"), current.recommended && /* @__PURE__ */ React.createElement(Tag, { color: "green" }, "\u63A8\u8350")),
      extra: /* @__PURE__ */ React.createElement(Space, null, !isCommon && /* @__PURE__ */ React.createElement(
        Button,
        {
          icon: /* @__PURE__ */ React.createElement(ExperimentOutlined, null),
          loading: testingKey === current.key,
          onClick: () => handleTest(current)
        },
        "\u6D4B\u8BD5\u8FDE\u901A"
      ), !isCommon && !current.builtin && /* @__PURE__ */ React.createElement(
        Popconfirm,
        {
          title: `\u5220\u9664\u5382\u5546\u300C${current.label}\u300D\uFF1F`,
          description: "\u5C06\u540C\u65F6\u5220\u9664\u5BF9\u5E94\u914D\u7F6E\u9879\uFF0C\u4E0D\u53EF\u6062\u590D",
          onConfirm: () => handleDelete(current)
        },
        /* @__PURE__ */ React.createElement(Button, { danger: true, icon: /* @__PURE__ */ React.createElement(DeleteOutlined, null) }, "\u5220\u9664")
      ), /* @__PURE__ */ React.createElement(
        Button,
        {
          type: "primary",
          icon: /* @__PURE__ */ React.createElement(SaveOutlined, null),
          loading: savingKey === current.key,
          onClick: () => saveCard(current)
        },
        "\u4FDD\u5B58"
      ))
    },
    !isCommon && current.key === "volcano" && /* @__PURE__ */ React.createElement(
      Alert,
      {
        style: { marginBottom: 16 },
        type: "warning",
        showIcon: true,
        message: "\u706B\u5C71\u5F15\u64CE\u9700\u586B\u63A8\u7406\u63A5\u5165\u70B9",
        description: "API Key \u7528\u65B9\u821F ARK_API_KEY\uFF1B\u6A21\u578B\u540D\u79F0\u586B\u63A7\u5236\u53F0\u63A5\u5165\u70B9 ID\uFF08ep-xxxxxxxx\uFF09\uFF0C\u4E0D\u662F\u6A21\u578B\u5C55\u793A\u540D\u3002"
      }
    ),
    !isCommon && current.key === "openai" && /* @__PURE__ */ React.createElement(
      Alert,
      {
        style: { marginBottom: 16 },
        type: "info",
        showIcon: true,
        message: "ChatGPT / GPT \u5B98\u65B9\u63A5\u6CD5",
        description: "\u5230 https://platform.openai.com/api-keys \u521B\u5EFA sk- \u5F00\u5934\u7684 API Key\uFF08\u9700\u5F00\u901A\u4ED8\u8D39/\u6709\u4F59\u989D\uFF09\u3002"
      }
    ),
    /* @__PURE__ */ React.createElement(Form, { layout: "vertical" }, visibleFields(current).map((item) => /* @__PURE__ */ React.createElement(Form.Item, { key: item.key, label: item.label, extra: item.description }, renderSettingField(item, values, setValues))), !visibleFields(current).length && /* @__PURE__ */ React.createElement(Alert, { type: "warning", message: "\u8BE5\u5382\u5546\u5C1A\u672A\u521D\u59CB\u5316\u914D\u7F6E\u9879\uFF0C\u8BF7\u5237\u65B0\u9875\u9762\u6216\u91CD\u542F\u540E\u7AEF\u3002" }))
  ))), /* @__PURE__ */ React.createElement(
    Modal,
    {
      title: "\u6DFB\u52A0\u5927\u6A21\u578B\u5382\u5546",
      open: addOpen,
      onOk: handleAdd,
      confirmLoading: adding,
      onCancel: () => setAddOpen(false),
      width: 560,
      destroyOnClose: true
    },
    /* @__PURE__ */ React.createElement(Form, { form, layout: "vertical", style: { marginTop: 8 } }, /* @__PURE__ */ React.createElement(
      Form.Item,
      {
        name: "key",
        label: "\u6807\u8BC6",
        rules: [
          { required: true, message: "\u5FC5\u586B" },
          { pattern: /^[a-z][a-z0-9_]{1,31}$/, message: "\u5C0F\u5199\u5B57\u6BCD\u5F00\u5934\uFF0C\u4EC5 a-z/0-9/_\uFF0C2-32 \u4F4D" }
        ],
        extra: "\u5982 myproxy\u3001local_llm\uFF0C\u521B\u5EFA\u540E\u4E0D\u53EF\u6539"
      },
      /* @__PURE__ */ React.createElement(Input2, { placeholder: "myproxy" })
    ), /* @__PURE__ */ React.createElement(Form.Item, { name: "label", label: "\u663E\u793A\u540D\u79F0", rules: [{ required: true }] }, /* @__PURE__ */ React.createElement(Input2, { placeholder: "\u6211\u7684\u4E2D\u8F6C" })), /* @__PURE__ */ React.createElement(Form.Item, { name: "desc", label: "\u7B80\u4ECB" }, /* @__PURE__ */ React.createElement(Input2, { placeholder: "\u53EF\u9009" })), /* @__PURE__ */ React.createElement(Form.Item, { name: "default_base_url", label: "\u9ED8\u8BA4 API Base URL", extra: "OpenAI \u517C\u5BB9\u6839\u5730\u5740" }, /* @__PURE__ */ React.createElement(Input2, { placeholder: "https://api.example.com/v1" })), /* @__PURE__ */ React.createElement(Form.Item, { name: "default_model", label: "\u9ED8\u8BA4\u6A21\u578B\u540D" }, /* @__PURE__ */ React.createElement(Input2, { placeholder: "gpt-4o-mini" })), /* @__PURE__ */ React.createElement(Form.Item, { name: "color", label: "\u6807\u7B7E\u989C\u8272" }, /* @__PURE__ */ React.createElement(Select2, { options: COLOR_OPTIONS })))
  ));
}
function PlatformsPage({ mod }) {
  const { reloadModules } = useOutletContext() || {};
  const [settings, setSettings] = useState({});
  const [readiness, setReadiness] = useState({});
  const [values, setValues] = useState({});
  const [loading, setLoading] = useState(true);
  const [savingKey, setSavingKey] = useState(null);
  const [testingKey, setTestingKey] = useState(null);
  const [activeKey, setActiveKey] = useState(null);
  const [addOpen, setAddOpen] = useState(false);
  const [adding, setAdding] = useState(false);
  const [form] = Form.useForm();
  const platforms = mod.platforms || [];
  const isCollector = mod.type === "collector_platforms";
  const isPublish = mod.type === "publish_platforms";
  const isCommercial = mod.type === "commercial_providers";
  const load = () => {
    setLoading(true);
    Promise.all([settingsApi.get(), settingsApi.check()]).then(([s, r]) => {
      setSettings(s);
      setReadiness(r);
      setValues(flattenValues(s));
      setActiveKey((prev) => {
        if (prev && platforms.some((p) => p.key === prev)) return prev;
        return platforms[0]?.key || null;
      });
    }).finally(() => setLoading(false));
  };
  useEffect(() => {
    load();
  }, [mod.key, platforms.map((p) => p.key).join(",")]);
  const savePlatform = (platform) => {
    const cat = platform.category;
    setSavingKey(platform.key);
    const all = groupValues(values);
    settingsApi.update({ [cat]: all[cat] || {} }).then(() => {
      message.success(`${platform.label} \u914D\u7F6E\u5DF2\u4FDD\u5B58`);
      load();
    }).catch(() => message.error("\u4FDD\u5B58\u5931\u8D25")).finally(() => setSavingKey(null));
  };
  const handleTestCommercial = (platform) => {
    setTestingKey(platform.key);
    const cat = platform.category;
    const all = groupValues(values);
    settingsApi.update({ [cat]: all[cat] || {} }).then(() => settingsApi.testCommercial(platform.key)).then((res) => {
      if (res.ok) {
        const sample = (res.items || []).map((i) => i.title).filter(Boolean).slice(0, 3).join("\uFF1B");
        message.success(`${res.message}${sample ? `\uFF1A${sample}` : ""}`);
        load();
      } else {
        message.error(res.message || "\u8BD5\u62C9\u5931\u8D25");
      }
    }).catch((err) => message.error(err?.message || err?.error || "\u8BD5\u62C9\u5931\u8D25")).finally(() => setTestingKey(null));
  };
  const handleAdd = () => {
    form.validateFields().then((vals) => {
      setAdding(true);
      const payload = {
        key: vals.key,
        label: vals.label,
        color: vals.color || "blue",
        desc: vals.desc || "",
        cookie_domain: vals.cookie_domain || "",
        creator_url: vals.creator_url || "",
        search_url_template: vals.search_url_template || "",
        enable_collector: !!vals.enable_collector,
        enable_publish: !!vals.enable_publish
      };
      platformsApi.create(payload).then((res) => {
        message.success(res.message || "\u5E73\u53F0\u5DF2\u6DFB\u52A0");
        setAddOpen(false);
        form.resetFields();
        return reloadModules?.();
      }).then(() => {
        setActiveKey(vals.key);
        load();
      }).catch((err) => message.error(err?.error || "\u6DFB\u52A0\u5931\u8D25")).finally(() => setAdding(false));
    });
  };
  const handleDelete = (platform) => {
    platformsApi.delete(platform.key).then((res) => {
      message.success(res.message || "\u5DF2\u5220\u9664");
      return reloadModules?.();
    }).then(() => {
      setActiveKey(null);
      load();
    }).catch((err) => message.error(err?.error || "\u5220\u9664\u5931\u8D25"));
  };
  if (loading) {
    return /* @__PURE__ */ React.createElement("div", { style: { textAlign: "center", padding: 60 } }, /* @__PURE__ */ React.createElement(Spin, null));
  }
  const moduleReady = readiness[mod.key];
  const current = platforms.find((p) => p.key === activeKey) || platforms[0];
  const statusTag = (ready) => {
    if (isCommercial) {
      if (ready?.enabled === false) return /* @__PURE__ */ React.createElement(Tag, { color: "orange" }, "\u5DF2\u5173\u95ED");
      if (ready?.ready && ready?.enabled) return /* @__PURE__ */ React.createElement(Tag, { color: "success" }, "API \u5DF2\u914D");
      if (ready?.enabled) return /* @__PURE__ */ React.createElement(Tag, { color: "warning" }, "\u5F85\u914D API");
      return /* @__PURE__ */ React.createElement(Tag, { color: "default" }, "\u672A\u542F\u7528");
    }
    return /* @__PURE__ */ React.createElement(React.Fragment, null, ready?.ready ? /* @__PURE__ */ React.createElement(Tag, { color: "success" }, isCollector ? "Cookies \u5DF2\u586B" : "\u5DF2\u542F\u7528") : /* @__PURE__ */ React.createElement(Tag, { color: "default" }, "\u672A\u914D\u7F6E"), ready && ready.enabled === false && /* @__PURE__ */ React.createElement(Tag, { color: "orange" }, "\u5DF2\u5173\u95ED"));
  };
  const alertDesc = isCommercial ? "\u586B\u5165\u5B98\u65B9/\u4F01\u4E1A API \u7684 Base URL\u3001Key\u3001\u699C\u5355\u8DEF\u5F84\u4E0E\u5B57\u6BB5\u6620\u5C04\uFF1B\u70B9\u300C\u8BD5\u62C9\u300D\u9A8C\u8BC1\u540E\uFF0C\u5230\u5185\u5BB9\u60C5\u62A5\u300C\u62C9\u5B98\u65B9\u6570\u636E\u53F0\u300D\u3002\u4E0D\u7528 Cookie \u722C\u7F51\u9875\u3002" : isCollector ? "\u3010\u91CD\u8981\u3011\u6296\u97F3/\u5C0F\u7EA2\u4E66\u7B49\u767B\u5F55\u6001\u81EA\u52A8\u91C7\u96C6\u6613\u5C01\u53F7\uFF0C\u9ED8\u8BA4\u5DF2\u5173\u95ED\u3002\u65E5\u5E38\u8BF7\u7528\u5185\u5BB9\u60C5\u62A5\u300C\u5168\u7F51\u70ED\u699C\u300D\u9009\u9898\u3002\u4EC5\u5B9E\u9A8C\u9700\u8981\u65F6\u518D\u5F00\u542F\u5E76\u586B\u5199 Cookies\u3002" : "\u63A8\u8350\uFF1A\u53D1\u5E03\u4E2D\u5FC3\u300C\u51C6\u5907\u53D1\u5E03\u300D\u590D\u5236\u6587\u6848\u5E76\u6253\u5F00\u5B98\u65B9\u521B\u4F5C\u8005\u9875\uFF0C\u7531\u4F60\u624B\u52A8\u70B9\u53D1\u8868\u3002Cookies / Playwright \u4EC5\u9AD8\u7EA7\u81EA\u52A8\u586B\u5145\u9700\u8981\uFF08\u6709\u5C01\u53F7\u98CE\u9669\uFF09\u3002";
  const typeTag = isCommercial ? "\u6570\u636E\u53F0" : isCollector ? "\u91C7\u96C6" : "\u53D1\u5E03";
  return /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("div", { style: { marginBottom: 16, display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, flexWrap: "wrap" } }, /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("div", { className: "page-title" }, mod.label), /* @__PURE__ */ React.createElement("div", { className: "page-desc", style: { marginBottom: 0 } }, mod.desc), moduleReady && /* @__PURE__ */ React.createElement(
    Alert,
    {
      style: { marginTop: 12 },
      type: isCollector ? "warning" : "info",
      showIcon: true,
      message: moduleReady.message,
      description: alertDesc
    }
  )), !isCommercial && /* @__PURE__ */ React.createElement(Button, { type: "primary", icon: /* @__PURE__ */ React.createElement(PlusOutlined, null), onClick: () => {
    form.resetFields();
    form.setFieldsValue({
      enable_collector: isCollector,
      enable_publish: isPublish,
      color: "blue"
    });
    setAddOpen(true);
  } }, "\u6DFB\u52A0\u5E73\u53F0")), /* @__PURE__ */ React.createElement("div", { className: "settings-plat-switch" }, platforms.map((p) => {
    const ready = readiness[p.category];
    const selected = current?.key === p.key;
    const on = isCommercial ? !!(ready?.ready && ready?.enabled) : !!ready?.ready;
    return /* @__PURE__ */ React.createElement(
      "button",
      {
        key: p.key,
        type: "button",
        className: `settings-plat-pill${selected ? " active" : ""}`,
        onClick: () => setActiveKey(p.key)
      },
      /* @__PURE__ */ React.createElement("span", { className: `dot ${on ? "on" : "off"}` }),
      p.label
    );
  })), !platforms.length && /* @__PURE__ */ React.createElement(Alert, { type: "info", message: "\u6682\u65E0\u5E73\u53F0\uFF0C\u70B9\u51FB\u53F3\u4E0A\u89D2\u6DFB\u52A0", style: { marginBottom: 14 } }), current && /* @__PURE__ */ React.createElement("div", { className: "settings-plat-meta" }, /* @__PURE__ */ React.createElement("span", { className: "meta-text" }, current.desc), statusTag(readiness[current.category])), /* @__PURE__ */ React.createElement("div", null, current && /* @__PURE__ */ React.createElement(
    Card,
    {
      title: /* @__PURE__ */ React.createElement(Space, null, current.label, /* @__PURE__ */ React.createElement(Tag, null, typeTag), !current.builtin && /* @__PURE__ */ React.createElement(Tag, { color: "processing" }, "\u81EA\u5B9A\u4E49")),
      extra: /* @__PURE__ */ React.createElement(Space, null, isCommercial && /* @__PURE__ */ React.createElement(
        Button,
        {
          icon: /* @__PURE__ */ React.createElement(ExperimentOutlined, null),
          loading: testingKey === current.key,
          onClick: () => handleTestCommercial(current)
        },
        "\u8BD5\u62C9"
      ), !isCommercial && !current.builtin && /* @__PURE__ */ React.createElement(
        Popconfirm,
        {
          title: `\u5220\u9664\u5E73\u53F0\u300C${current.label}\u300D\uFF1F`,
          description: "\u5C06\u540C\u65F6\u5220\u9664\u5BF9\u5E94\u914D\u7F6E\u9879\uFF0C\u4E0D\u53EF\u6062\u590D",
          onConfirm: () => handleDelete(current)
        },
        /* @__PURE__ */ React.createElement(Button, { danger: true, icon: /* @__PURE__ */ React.createElement(DeleteOutlined, null) }, "\u5220\u9664")
      ), /* @__PURE__ */ React.createElement(
        Button,
        {
          type: "primary",
          icon: /* @__PURE__ */ React.createElement(SaveOutlined, null),
          loading: savingKey === current.key,
          onClick: () => savePlatform(current),
          title: "\u4FDD\u5B58"
        },
        "\u4FDD\u5B58"
      ))
    },
    !isCommercial && !current.builtin && /* @__PURE__ */ React.createElement(
      Alert,
      {
        style: { marginBottom: 16 },
        type: "info",
        showIcon: true,
        message: isCollector ? `\u641C\u7D22\u6A21\u677F\uFF1A${current.search_url_template || "\u672A\u586B"}\uFF1BCookie \u57DF\u540D\uFF1A${current.cookie_domain || "\u81EA\u52A8"}` : `\u521B\u4F5C\u8005\u540E\u53F0\uFF1A${current.creator_url || "\u672A\u586B"}\uFF1BCookie \u57DF\u540D\uFF1A${current.cookie_domain || "\u81EA\u52A8"}`
      }
    ),
    /* @__PURE__ */ React.createElement(Form, { layout: "vertical" }, (settings[current.category] || []).map((item) => /* @__PURE__ */ React.createElement(Form.Item, { key: item.key, label: item.label, extra: item.description }, renderSettingField(item, values, setValues))), !(settings[current.category] || []).length && /* @__PURE__ */ React.createElement(Alert, { type: "warning", message: "\u8BE5\u5E73\u53F0\u5C1A\u672A\u521D\u59CB\u5316\u914D\u7F6E\u9879\uFF0C\u8BF7\u5237\u65B0\u9875\u9762\u6216\u91CD\u542F\u540E\u7AEF\u4EE5\u5199\u5165\u9ED8\u8BA4\u914D\u7F6E\u3002" }))
  )), !isCommercial && /* @__PURE__ */ React.createElement(
    Modal,
    {
      title: "\u6DFB\u52A0\u5E73\u53F0",
      open: addOpen,
      onOk: handleAdd,
      confirmLoading: adding,
      onCancel: () => setAddOpen(false),
      width: 640,
      destroyOnClose: true
    },
    /* @__PURE__ */ React.createElement(Form, { form, layout: "vertical", style: { marginTop: 8 } }, /* @__PURE__ */ React.createElement(Form.Item, { name: "key", label: "\u5E73\u53F0\u6807\u8BC6", rules: [
      { required: true, message: "\u5FC5\u586B" },
      { pattern: /^[a-z][a-z0-9_]{1,31}$/, message: "\u5C0F\u5199\u5B57\u6BCD\u5F00\u5934\uFF0C\u4EC5 a-z/0-9/_\uFF0C2-32 \u4F4D" }
    ], extra: "\u5982 kuaishou\u3001bilibili\uFF0C\u521B\u5EFA\u540E\u4E0D\u53EF\u6539" }, /* @__PURE__ */ React.createElement(Input2, { placeholder: "kuaishou" })), /* @__PURE__ */ React.createElement(Form.Item, { name: "label", label: "\u663E\u793A\u540D\u79F0", rules: [{ required: true }] }, /* @__PURE__ */ React.createElement(Input2, { placeholder: "\u5FEB\u624B" })), /* @__PURE__ */ React.createElement(Form.Item, { name: "desc", label: "\u7B80\u4ECB" }, /* @__PURE__ */ React.createElement(Input2, { placeholder: "\u53EF\u9009" })), /* @__PURE__ */ React.createElement(Form.Item, { name: "color", label: "\u6807\u7B7E\u989C\u8272" }, /* @__PURE__ */ React.createElement(Select2, { options: COLOR_OPTIONS })), /* @__PURE__ */ React.createElement(Form.Item, { name: "cookie_domain", label: "Cookie \u57DF\u540D", extra: "\u5982 .kuaishou.com\uFF1B\u4E0D\u586B\u5219\u4ECE URL \u81EA\u52A8\u63A8\u65AD" }, /* @__PURE__ */ React.createElement(Input2, { placeholder: ".kuaishou.com" })), /* @__PURE__ */ React.createElement(Form.Item, { name: "enable_collector", valuePropName: "checked" }, /* @__PURE__ */ React.createElement(Checkbox, null, "\u7528\u4E8E\u91C7\u96C6")), /* @__PURE__ */ React.createElement(
      Form.Item,
      {
        noStyle: true,
        shouldUpdate: (prev, cur) => prev.enable_collector !== cur.enable_collector
      },
      ({ getFieldValue }) => getFieldValue("enable_collector") ? /* @__PURE__ */ React.createElement(
        Form.Item,
        {
          name: "search_url_template",
          label: "\u641C\u7D22\u9875 URL \u6A21\u677F",
          rules: [{ required: true, message: "\u91C7\u96C6\u9700\u8981\u641C\u7D22\u6A21\u677F" }],
          extra: "\u5FC5\u987B\u5305\u542B {keyword}\uFF0C\u4F8B\u5982 https://www.kuaishou.com/search/video?searchKey={keyword}"
        },
        /* @__PURE__ */ React.createElement(Input2, { placeholder: "https://www.example.com/search?q={keyword}" })
      ) : null
    ), /* @__PURE__ */ React.createElement(Form.Item, { name: "enable_publish", valuePropName: "checked" }, /* @__PURE__ */ React.createElement(Checkbox, null, "\u7528\u4E8E\u53D1\u5E03")), /* @__PURE__ */ React.createElement(
      Form.Item,
      {
        noStyle: true,
        shouldUpdate: (prev, cur) => prev.enable_publish !== cur.enable_publish
      },
      ({ getFieldValue }) => getFieldValue("enable_publish") ? /* @__PURE__ */ React.createElement(
        Form.Item,
        {
          name: "creator_url",
          label: "\u521B\u4F5C\u8005\u540E\u53F0\u5730\u5740",
          rules: [{ required: true, message: "\u53D1\u5E03\u9700\u8981\u521B\u4F5C\u8005\u540E\u53F0 URL" }],
          extra: "\u53D1\u5E03\u65F6\u4F1A\u6253\u5F00\u6B64\u9875\u9762\u5E76\u6CE8\u5165 Cookies"
        },
        /* @__PURE__ */ React.createElement(Input2, { placeholder: "https://cp.kuaishou.com/article/publish/video" })
      ) : null
    ))
  ));
}
function ScheduledTasksPage() {
  const [list, setList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState(null);
  const [editTask, setEditTask] = useState(null);
  const [hour, setHour] = useState(8);
  const load = () => {
    setLoading(true);
    settingsApi.scheduledTasks().then((res) => setList(res.list || [])).catch(() => message.error("\u52A0\u8F7D\u5B9A\u65F6\u4EFB\u52A1\u5931\u8D25")).finally(() => setLoading(false));
  };
  useEffect(() => {
    load();
  }, []);
  const toggle = (row) => {
    setBusyId(row.id);
    settingsApi.updateScheduledTask(row.id, { enabled: !row.enabled }).then(() => {
      message.success(row.enabled ? "\u5DF2\u6682\u505C" : "\u5DF2\u542F\u7528");
      load();
    }).catch((err) => message.error(err?.error || "\u66F4\u65B0\u5931\u8D25")).finally(() => setBusyId(null));
  };
  const saveHour = () => {
    if (!editTask) return;
    setBusyId(editTask.id);
    settingsApi.updateScheduledTask(editTask.id, { hour }).then(() => {
      message.success("\u6267\u884C\u6574\u70B9\u5DF2\u66F4\u65B0");
      setEditTask(null);
      load();
    }).catch((err) => message.error(err?.error || "\u66F4\u65B0\u5931\u8D25")).finally(() => setBusyId(null));
  };
  const columns = [
    {
      title: "\u4EFB\u52A1\u540D\u79F0",
      dataIndex: "name",
      render: (v, r) => /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("div", { style: { fontWeight: 600, color: "var(--color-primary, #5b5bd6)" } }, v), /* @__PURE__ */ React.createElement("div", { style: { fontSize: 12, color: "#9b9bb0", marginTop: 2 } }, r.desc))
    },
    { title: "\u6267\u884C\u9891\u7387", dataIndex: "frequency", width: 140 },
    { title: "\u4E0B\u6B21\u6267\u884C", dataIndex: "next_run", width: 120 },
    {
      title: "\u72B6\u6001",
      dataIndex: "status",
      width: 100,
      render: (v) => v === "running" ? /* @__PURE__ */ React.createElement(Tag, { color: "success" }, "\u8FD0\u884C\u4E2D") : /* @__PURE__ */ React.createElement(Tag, null, "\u5DF2\u6682\u505C")
    },
    {
      title: "\u64CD\u4F5C",
      key: "action",
      width: 120,
      render: (_, r) => /* @__PURE__ */ React.createElement(Space, null, /* @__PURE__ */ React.createElement(
        Button,
        {
          size: "small",
          icon: r.enabled ? /* @__PURE__ */ React.createElement(PauseCircleOutlined, null) : /* @__PURE__ */ React.createElement(PlayCircleOutlined, null),
          loading: busyId === r.id,
          onClick: () => toggle(r)
        }
      ), /* @__PURE__ */ React.createElement(
        Button,
        {
          size: "small",
          icon: /* @__PURE__ */ React.createElement(EditOutlined, null),
          onClick: () => {
            setEditTask(r);
            setHour(r.hour ?? 8);
          }
        }
      ))
    }
  ];
  return /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 } }, /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("div", { className: "page-title" }, "\u5B9A\u65F6\u4EFB\u52A1"), /* @__PURE__ */ React.createElement("div", { className: "page-desc", style: { marginBottom: 0 } }, "\u7BA1\u7406\u65E5\u66F4\u3001\u8D22\u7ECF\u65B0\u95FB\u3001\u5168\u5E02\u573A\u540C\u6B65\u4E0E\u81EA\u9009\u80A1\u5237\u65B0\u7B49\u540E\u53F0\u4EFB\u52A1\u3002")), /* @__PURE__ */ React.createElement(Button, { icon: /* @__PURE__ */ React.createElement(ExperimentOutlined, null), onClick: load }, "\u5237\u65B0")), /* @__PURE__ */ React.createElement(Card, { styles: { body: { padding: 0 } } }, /* @__PURE__ */ React.createElement(
    Table,
    {
      rowKey: "id",
      columns,
      dataSource: list,
      loading,
      pagination: false,
      size: "middle"
    }
  )), /* @__PURE__ */ React.createElement(
    Modal,
    {
      title: `\u8C03\u6574\u6267\u884C\u6574\u70B9 \u2014 ${editTask?.name || ""}`,
      open: !!editTask,
      onOk: saveHour,
      onCancel: () => setEditTask(null),
      confirmLoading: busyId === editTask?.id,
      destroyOnClose: true
    },
    /* @__PURE__ */ React.createElement(Form, { layout: "vertical", style: { marginTop: 12 } }, /* @__PURE__ */ React.createElement(Form.Item, { label: "\u6267\u884C\u6574\u70B9\uFF080-23\uFF09", extra: "\u5230\u70B9\u540E\u7EA6 10 \u5206\u949F\u7A97\u53E3\u5185\u6267\u884C\u4E00\u6B21" }, /* @__PURE__ */ React.createElement(InputNumber, { min: 0, max: 23, value: hour, onChange: (v) => setHour(v ?? 0), style: { width: 120 } })), editTask?.last_run ? /* @__PURE__ */ React.createElement("div", { style: { color: "#94a3b8", fontSize: 12 } }, "\u4E0A\u6B21\u6267\u884C\uFF1A", editTask.last_run) : null)
  ));
}
export {
  SettingsModulePage as default
};
