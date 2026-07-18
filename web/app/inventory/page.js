"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { apiGet, apiPost, getOrCreateDeviceId, statusLabelToClass } from "../../lib/api";

export default function InventoryPage() {
  const [deviceId, setDeviceId] = useState("");
  const [query, setQuery] = useState("");
  const [items, setItems] = useState([]);
  const [info, setInfo] = useState("");

  async function load(id, q = "") {
    const data = await apiGet(`/search/${id}?q=${encodeURIComponent(q)}`);
    setItems(data.filter((x) => x.has_stock));
  }

  useEffect(() => {
    const id = getOrCreateDeviceId();
    setDeviceId(id);
    load(id);
  }, []);

  async function reduce(itemId) {
    const out = await apiPost(`/inventory/${itemId}/reduce`, { device_id: deviceId, amount: 1 });
    setInfo(`${out.name} 수량 차감 완료`);
    await load(deviceId, query);
  }

  async function discard(itemId) {
    const out = await apiPost(`/inventory/${itemId}/discard`, { device_id: deviceId, amount: 1 });
    setInfo(`${out.name} 폐기 처리 완료`);
    await load(deviceId, query);
  }

  return (
    <main className="shell">
      <section className="hero">
        <h1>재고 관리</h1>
        <p>수량 차감, 전량 폐기, 임박/기한 지남 우선 확인</p>
        <nav className="nav">
          <Link href="/">대시보드</Link>
          <Link href="/register">식재료 등록</Link>
        </nav>
      </section>

      <section className="grid">
        <article className="card">
          <div className="row">
            <div className="row">
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="식재료명"
                style={{ width: 280 }}
              />
              <button onClick={() => load(deviceId, query)}>검색</button>
            </div>
          </div>
          {info && <p>{info}</p>}

          <div className="list">
            {items.length === 0 && <p>표시할 보유 재고가 없습니다.</p>}
            {items
              .slice()
              .sort((a, b) => {
                const score = (x) => (x.status === "기한 지남" ? 2 : x.status === "임박" ? 1 : 0);
                return score(b) - score(a);
              })
              .map((it) => (
                <div key={it.item_id} className="card">
                  <div className="row">
                    <div>
                      <strong>{it.name}</strong> · 수량 {it.total_qty}
                    </div>
                    <span className={statusLabelToClass(it.status)}>{it.status}</span>
                  </div>
                  <div className="row" style={{ marginTop: 10 }}>
                    <button onClick={() => reduce(it.item_id)}>수량 -1</button>
                    <button className="warn" onClick={() => discard(it.item_id)}>
                      전량 폐기
                    </button>
                  </div>
                </div>
              ))}
          </div>
        </article>
      </section>
    </main>
  );
}
