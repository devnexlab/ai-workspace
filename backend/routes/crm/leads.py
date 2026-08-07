"""线索池路由。"""

from flask import Blueprint, request, jsonify
from config import get_db as _db
from modules.leads import (
    LEAD_FIELDS,
    SOURCE_OPTIONS,
    STATUS_OPTIONS,
    create_lead_row,
    convert_lead_to_customer,
    serialize_lead,
)

bp = Blueprint('leads', __name__)


@bp.route('/api/leads/meta')
def leads_meta():
    return jsonify({
        'sources': SOURCE_OPTIONS,
        'statuses': STATUS_OPTIONS,
    })


@bp.route('/api/leads')
def list_leads():
    conn = _db()
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('pageSize', 20))
    status = (request.args.get('status') or '').strip()
    source = (request.args.get('source') or '').strip()
    q = (request.args.get('q') or '').strip()

    where = []
    params = []
    # 已转化进入客户列表，默认不再出现在线索池
    if status == 'converted':
        where.append("status='converted'")
    else:
        where.append("status<>'converted'")
        if status:
            where.append('status=?')
            params.append(status)
    if source:
        if source == 'content':
            where.append("source IN ('douyin','xiaohongshu','channels')")
        else:
            where.append('source=?')
            params.append(source)
    if q:
        where.append('(nickname LIKE ? OR phone LIKE ? OR wechat LIKE ? OR remark LIKE ?)')
        params.extend([f'%{q}%'] * 4)

    where_clause = ('WHERE ' + ' AND '.join(where)) if where else ''
    offset = (page - 1) * page_size

    total = conn.execute(
        f'SELECT COUNT(*) as c FROM lead {where_clause}', params
    ).fetchone()['c']

    rows = conn.execute(
        f'''SELECT * FROM lead {where_clause}
            ORDER BY
              CASE status
                WHEN 'pending_contact' THEN 0
                WHEN 'following' THEN 1
                ELSE 2
              END,
              created_at DESC
            LIMIT ? OFFSET ?''',
        params + [page_size, offset],
    ).fetchall()

    stats = {
        'today_new': 0,
        'pending_contact': 0,
        'following': 0,
        'converted_week': 0,
        'invalid': 0,
    }
    for r in conn.execute(
        '''SELECT
             COUNT(*) FILTER (WHERE created_at::date = CURRENT_DATE) AS today_new,
             COUNT(*) FILTER (WHERE status = 'pending_contact') AS pending_contact,
             COUNT(*) FILTER (WHERE status = 'following') AS following,
             COUNT(*) FILTER (
               WHERE status = 'converted'
                 AND updated_at::date >= CURRENT_DATE - INTERVAL '6 days'
             ) AS converted_week,
             COUNT(*) FILTER (WHERE status = 'invalid') AS invalid
           FROM lead'''
    ).fetchall():
        stats = {
            'today_new': r['today_new'] or 0,
            'pending_contact': r['pending_contact'] or 0,
            'following': r['following'] or 0,
            'converted_week': r['converted_week'] or 0,
            'invalid': r['invalid'] or 0,
        }

    conn.close()
    return jsonify({
        'list': [serialize_lead(r) for r in rows],
        'total': total,
        'page': page,
        'pageSize': page_size,
        'stats': stats,
    })


@bp.route('/api/leads/<int:id>')
def get_lead(id):
    conn = _db()
    row = conn.execute('SELECT * FROM lead WHERE id=?', (id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({'error': 'not found'}), 404
    return jsonify(serialize_lead(row))


@bp.route('/api/leads', methods=['POST'])
def create_lead():
    data = request.get_json(silent=True) or {}
    try:
        result = create_lead_row(data, notify=False)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    return jsonify({**result, 'message': '线索已创建'}), 201


@bp.route('/api/leads/<int:id>', methods=['PUT'])
def update_lead(id):
    data = request.get_json(silent=True) or {}
    conn = _db()
    row = conn.execute('SELECT * FROM lead WHERE id=?', (id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'not found'}), 404

    fields = []
    values = []
    for key in LEAD_FIELDS:
        if key not in data:
            continue
        val = data[key]
        if key == 'nickname':
            val = (val or '').strip()
            if not val:
                conn.close()
                return jsonify({'error': '称呼不能为空'}), 400
        if key == 'source' and val not in {x['value'] for x in SOURCE_OPTIONS}:
            conn.close()
            return jsonify({'error': '来源无效'}), 400
        if key == 'status' and val not in {x['value'] for x in STATUS_OPTIONS}:
            conn.close()
            return jsonify({'error': '状态无效'}), 400
        fields.append(f'{key}=?')
        values.append(val if val is not None else '')

    if not fields:
        conn.close()
        return jsonify({'error': 'no fields'}), 400

    fields.append('updated_at=CURRENT_TIMESTAMP')
    values.append(id)
    conn.execute(f"UPDATE lead SET {', '.join(fields)} WHERE id=?", values)
    conn.commit()
    updated = conn.execute('SELECT * FROM lead WHERE id=?', (id,)).fetchone()
    conn.close()
    return jsonify({'message': '已保存', 'item': serialize_lead(updated)})


@bp.route('/api/leads/<int:id>/convert', methods=['POST'])
def convert_lead(id):
    try:
        result = convert_lead_to_customer(id)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'转化失败: {e}'}), 500
    return jsonify(result)


@bp.route('/api/leads/batch-convert', methods=['POST'])
def batch_convert():
    data = request.get_json(silent=True) or {}
    ids = data.get('ids') or []
    if not isinstance(ids, list) or not ids:
        return jsonify({'error': '请选择线索'}), 400
    ok, fail = [], []
    for lid in ids:
        try:
            ok.append(convert_lead_to_customer(int(lid)))
        except Exception as e:
            fail.append({'id': lid, 'error': str(e)})
    return jsonify({
        'message': f'成功 {len(ok)} 条，失败 {len(fail)} 条',
        'ok': ok,
        'fail': fail,
    })


@bp.route('/api/leads/<int:id>', methods=['DELETE'])
def delete_lead(id):
    conn = _db()
    conn.execute('DELETE FROM lead WHERE id=?', (id,))
    conn.commit()
    conn.close()
    return jsonify({'message': '已删除'})
