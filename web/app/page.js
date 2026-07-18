"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { apiGet, apiPost, getApiBase, getOrCreateDeviceId, statusLabelToClass } from "../lib/api";

function base64UrlToUint8Array(base64UrlString) {
  const padding = "=".repeat((4 - (base64UrlString.length % 4)) % 4);
  const base64 = (base64UrlString + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = atob(base64);
  return Uint8Array.from([...rawData].map((ch) => ch.charCodeAt(0)));
}

export default function HomePage() {
  const [deviceId, setDeviceId] = useState("");
  const [items, setItems] = useState([]);
  const [selectedSummaryStatus, setSelectedSummaryStatus] = useState("");
  const [showAllInventory, setShowAllInventory] = useState(false);
  const [expandedItemId, setExpandedItemId] = useState("");
  const [itemDetail, setItemDetail] = useState(null);
  const [error, setError] = useState("");
  const [pushHint, setPushHint] = useState("");
  const [isEnablingPush, setIsEnablingPush] = useState(false);
  const [alertPolicy, setAlertPolicy] = useState({
    push_permission_denied: false,
    show_permission_modal: false,
    persistent_warning_banner: false,
  });

  async function loadAll(currentDeviceId) {
    try {
      await apiPost("/device/register", { device_id: currentDeviceId });
      const result = await apiGet(`/search/${currentDeviceId}?q=`);
      const alerts = await apiGet(`/dashboard/${currentDeviceId}/alerts`);
      setItems(result.filter((x) => x.has_stock));
      setAlertPolicy(alerts);
      setError("");
    } catch (e) {
      setError(String(e.message || e));
    }
  }

  async function syncPermission(currentDeviceId, stateOverride) {
    if (typeof Notification === "undefined") {
      return;
    }
    const state = stateOverride || Notification.permission;
    await fetch(`${getApiBase()}/device/${currentDeviceId}/push-permission`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ state }),
    });
  }

  async function runD3Batch() {
    await fetch(`${getApiBase()}/notifications/d3/run`, { method: "POST" });
  }

  async function enablePushFlow() {
    if (!deviceId) return;
    if (typeof Notification === "undefined") {
      setPushHint("이 브라우저는 알림 기능을 지원하지 않습니다.");
      return;
    }
    if (!("serviceWorker" in navigator) || !window.PushManager) {
      setPushHint("현재 브라우저에서는 웹푸시를 사용할 수 없습니다. 일반 브라우저 또는 홈 화면 앱에서 시도해 주세요.");
      return;
    }

    setIsEnablingPush(true);
    try {
      const state = await Notification.requestPermission();
      await syncPermission(deviceId, state);

      if (state !== "granted") {
        setPushHint("알림이 차단되어 있습니다. 브라우저 사이트 설정에서 알림을 허용해 주세요.");
        await loadAll(deviceId);
        return;
      }

      await upsertPushSubscription(deviceId);
      await runD3Batch();
      await loadAll(deviceId);
      setPushHint("푸시 권한 허용 및 구독이 완료되었습니다. 임박 재고가 있으면 알림이 발송됩니다.");
    } catch (e) {
      const msg = String(e?.message || e || "");
      if (msg.includes("incognito")) {
        setPushHint("시크릿 모드에서는 푸시 구독이 제한됩니다. 일반 브라우저 창에서 다시 시도해 주세요.");
      } else {
        setPushHint("푸시 권한/구독 설정 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.");
      }
    } finally {
      setIsEnablingPush(false);
    }
  }

  async function upsertPushSubscription(currentDeviceId) {
    if (typeof window === "undefined") return;
    if (!("serviceWorker" in navigator)) return;
    if (!window.PushManager) return;
    if (typeof Notification === "undefined" || Notification.permission !== "granted") return;

    const registration = await navigator.serviceWorker.ready;
    let subscription = await registration.pushManager.getSubscription();
    const vapidPublicKey = process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY || "";

    if (subscription && vapidPublicKey) {
      // Recreate subscription after key rotation so server private/public keys stay aligned.
      await subscription.unsubscribe();
      subscription = null;
    }

    if (!subscription) {
      const subscribeOptions = { userVisibleOnly: true };
      if (vapidPublicKey) {
        subscribeOptions.applicationServerKey = base64UrlToUint8Array(vapidPublicKey);
      }
      subscription = await registration.pushManager.subscribe(subscribeOptions);
    }

    const json = subscription.toJSON();
    if (!json.endpoint || !json.keys?.p256dh || !json.keys?.auth) {
      return;
    }

    await fetch(`${getApiBase()}/device/${currentDeviceId}/push-subscription`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        endpoint: json.endpoint,
        keys: {
          p256dh: json.keys.p256dh,
          auth: json.keys.auth,
        },
      }),
    });
    setPushHint("");
  }

  async function toggleItemDetail(itemId) {
    if (!deviceId) return;
    if (expandedItemId === itemId) {
      setExpandedItemId("");
      setItemDetail(null);
      return;
    }

    const detail = await apiGet(`/inventory/${deviceId}/${itemId}`);
    setExpandedItemId(itemId);
    setItemDetail(detail);
  }

  useEffect(() => {
    async function boot() {
      const id = getOrCreateDeviceId();
      setDeviceId(id);
      await loadAll(id);

      if (typeof Notification === "undefined") {
        return;
      }

      const state = Notification.permission;
      await syncPermission(id, state);
      if (state === "granted") {
        try {
          await upsertPushSubscription(id);
        } catch (e) {
          const msg = String(e?.message || e || "");
          if (msg.includes("incognito")) {
            setPushHint("시크릿 모드에서는 웹푸시 구독이 제한됩니다. 일반 브라우저 창에서 이용해 주세요.");
          } else {
            setPushHint("웹푸시 구독 생성에 실패했습니다. 일반 브라우저 창에서 다시 시도해 주세요.");
          }
          // keep page usable even when browser push subscription setup fails
        }
        await runD3Batch();
      }
      await loadAll(id);
    }

    boot();
  }, []);

  const summary = useMemo(() => {
    const owned = items.filter((x) => x.status === "보유").length;
    const imminent = items.filter((x) => x.status === "임박").length;
    const risk = items.filter((x) => x.status === "기한 지남").length;
    return { owned, imminent, risk };
  }, [items]);

  const summaryItems = useMemo(
    () => items.filter((x) => x.status === selectedSummaryStatus),
    [items, selectedSummaryStatus],
  );

  function toggleSummaryStatus(status) {
    setSelectedSummaryStatus((prev) => (prev === status ? "" : status));
  }

  const visibleItems = useMemo(() => {
    if (showAllInventory) {
      return items;
    }
    return items.slice(0, 5);
  }, [items, showAllInventory]);

  function toggleShowAllInventory() {
    if (showAllInventory) {
      const firstFiveIds = new Set(items.slice(0, 5).map((x) => x.item_id));
      if (expandedItemId && !firstFiveIds.has(expandedItemId)) {
        setExpandedItemId("");
        setItemDetail(null);
      }
      setShowAllInventory(false);
      return;
    }
    setShowAllInventory(true);
  }

  return (
    <main className="shell">
      <section className="hero">
        <nav className="nav">
          <Link href="/register">식재료 등록</Link>
          <Link href="/inventory">재고 관리</Link>
        </nav>
        {alertPolicy.persistent_warning_banner && (
          <div className="banner">
            푸시 권한이 없어서 앱 내 배너로 임박/기한 지남 항목을 안내합니다.
            <div className="banner-actions">
              <button className="primary" onClick={enablePushFlow} disabled={isEnablingPush}>
                {isEnablingPush ? "권한 설정 중..." : "푸시 권한 요청"}
              </button>
            </div>
          </div>
        )}
        {alertPolicy.show_permission_modal && (
          <div className="banner">
            임박 재고 알림을 받으려면 푸시 권한이 필요합니다.
            <div className="banner-actions">
              <button className="primary" onClick={enablePushFlow} disabled={isEnablingPush}>
                {isEnablingPush ? "권한 설정 중..." : "푸시 권한 요청"}
              </button>
            </div>
          </div>
        )}
        {pushHint && <div className="banner">{pushHint}</div>}
      </section>

      <section className="grid">
        <article className="card card-half">
          <h3>상태 요약</h3>
          <div className="summary-filter-row">
            <button
              className={selectedSummaryStatus === "보유" ? "summary-filter summary-filter-active" : "summary-filter"}
              onClick={() => toggleSummaryStatus("보유")}
            >
              보유 {summary.owned}
            </button>
            <button
              className={selectedSummaryStatus === "임박" ? "summary-filter summary-filter-active" : "summary-filter"}
              onClick={() => toggleSummaryStatus("임박")}
            >
              임박 {summary.imminent}
            </button>
            <button
              className={
                selectedSummaryStatus === "기한 지남" ? "summary-filter summary-filter-active" : "summary-filter"
              }
              onClick={() => toggleSummaryStatus("기한 지남")}
            >
              기한 지남 {summary.risk}
            </button>
          </div>
          <div style={{ marginTop: 10 }}>
            {!selectedSummaryStatus && <p className="fine">상태를 클릭하면 해당 식재료가 표시됩니다.</p>}
            {selectedSummaryStatus && summaryItems.length === 0 && <p className="fine">해당 상태 식재료가 없습니다.</p>}
            {selectedSummaryStatus && summaryItems.length > 0 && (
              <div className="summary-item-list">
                {summaryItems.map((it) => (
                  <span key={it.item_id} className={statusLabelToClass(it.status)}>
                    {it.name} · {it.total_qty}
                  </span>
                ))}
              </div>
            )}
          </div>
        </article>
        <article className="card">
          <div className="row">
            <h3>전체 재고</h3>
            <button onClick={() => loadAll(deviceId)}>새로고침</button>
          </div>
          {error && <p>{error}</p>}
          <div className="list">
            {items.length === 0 && <p>등록된 품목이 없습니다. 등록 화면에서 추가해 주세요.</p>}
            {visibleItems.map((it) => (
              <div key={it.item_id} className="card">
                <div className="row">
                  <div>
                    <button
                      onClick={() => toggleItemDetail(it.item_id)}
                      style={{ background: "transparent", border: "none", padding: 0, fontWeight: 700 }}
                    >
                      {it.name}
                    </button>{" "}
                    · {it.total_qty}
                  </div>
                  <span className={statusLabelToClass(it.status)}>{it.status}</span>
                </div>
                {expandedItemId === it.item_id && itemDetail && (
                  <div style={{ marginTop: 10 }}>
                    <div className="fine">유통기한 목록</div>
                    {itemDetail.batches
                      .filter((b) => b.qty > 0)
                      .map((b) => (
                        <div key={b.batch_id} className="row" style={{ marginTop: 6 }}>
                          <span>{b.expiry_date}</span>
                          <span>
                            수량 {b.qty} · {b.status}
                          </span>
                        </div>
                      ))}
                  </div>
                )}
              </div>
            ))}
            {items.length > 5 && (
              <button className="more-toggle" onClick={toggleShowAllInventory}>
                {showAllInventory ? "나머지 재고 접기 ▲" : `나머지 재고 더보기 ▼ (${items.length - 5}개)`}
              </button>
            )}
          </div>
        </article>
      </section>
    </main>
  );
}
