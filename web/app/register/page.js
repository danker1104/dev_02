"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { apiPost, getApiBase, getOrCreateDeviceId } from "../../lib/api";

const initial = {
  name: "",
  expiry_date: "",
  qty: 1,
};

export default function RegisterPage() {
  const [form, setForm] = useState(initial);
  const [message, setMessage] = useState("");
  const [ocrMessage, setOcrMessage] = useState("");
  const [visionFileName, setVisionFileName] = useState("");
  const [visionFile, setVisionFile] = useState(null);
  const [isMobileDevice, setIsMobileDevice] = useState(false);
  const [isOcrLoading, setIsOcrLoading] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const ua = window.navigator.userAgent || "";
    const byUa = /Android|iPhone|iPad|iPod|Mobile/i.test(ua);
    const byPointer = window.matchMedia?.("(pointer: coarse)")?.matches ?? false;
    setIsMobileDevice(byUa || byPointer);
  }, []);

  function onVisionFileSelected(file) {
    setVisionFile(file);
    setVisionFileName(file?.name || "");
    setForm(initial);
    setMessage("");
    setOcrMessage("");
  }

  function mapOcrFailReason(reason) {
    if (reason === "missing_file") return "이미지를 먼저 선택해 주세요.";
    if (reason === "empty_file") return "이미지 파일을 읽지 못했습니다. 다른 파일로 다시 시도해 주세요.";
    if (reason === "missing_api_key") return "OCR 설정이 비어 있습니다. 서버의 OCR_API_KEY를 설정해 주세요.";
    if (reason === "request_failed") return "Vision 서비스 호출에 실패했습니다. 잠시 후 다시 시도해 주세요.";
    if (reason === "empty_parsed_results") return "이미지에서 텍스트를 찾지 못했습니다. 글자가 선명한 사진으로 다시 시도해 주세요.";
    if (reason === "name_not_found") return "텍스트는 읽었지만 식재료명을 찾지 못했습니다. 수동 입력으로 진행해 주세요.";
    return "Vision 인식 결과를 가져오지 못했습니다. 아래 수동 입력으로 계속 진행해 주세요.";
  }

  function readImageDimensions(file) {
    return new Promise((resolve, reject) => {
      const url = URL.createObjectURL(file);
      const img = new Image();
      img.onload = () => {
        const dims = { width: img.naturalWidth, height: img.naturalHeight, img, url };
        resolve(dims);
      };
      img.onerror = () => {
        URL.revokeObjectURL(url);
        reject(new Error("image_load_failed"));
      };
      img.src = url;
    });
  }

  async function prepareImageForOcr(file) {
    const isImage = file?.type?.startsWith("image/");
    if (!isImage) return file;

    const MAX_EDGE = 1600;
    const JPEG_QUALITY = 0.82;

    const { width, height, img, url } = await readImageDimensions(file);
    const scale = Math.min(1, MAX_EDGE / Math.max(width, height));
    const targetWidth = Math.max(1, Math.round(width * scale));
    const targetHeight = Math.max(1, Math.round(height * scale));

    const canvas = document.createElement("canvas");
    canvas.width = targetWidth;
    canvas.height = targetHeight;

    const ctx = canvas.getContext("2d");
    if (!ctx) {
      URL.revokeObjectURL(url);
      return file;
    }

    ctx.drawImage(img, 0, 0, targetWidth, targetHeight);
    URL.revokeObjectURL(url);

    const blob = await new Promise((resolve, reject) => {
      canvas.toBlob((result) => {
        if (result) {
          resolve(result);
          return;
        }
        reject(new Error("image_encode_failed"));
      }, "image/jpeg", JPEG_QUALITY);
    });

    return blob;
  }

  async function runMockOcr() {
    if (!visionFile) {
      setOcrMessage("이미지를 먼저 선택해 주세요.");
      return;
    }

    setIsOcrLoading(true);
    setOcrMessage("이미지를 인식하는 중입니다. 잠시만 기다려 주세요.");

    const formData = new FormData();
    const uploadBlob = await prepareImageForOcr(visionFile);
    formData.append("file", uploadBlob, `${Date.now()}-vision.jpg`);

    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), 15000);

    try {
      const res = await fetch(`${getApiBase()}/ocr/mock`, {
        method: "POST",
        body: formData,
        signal: controller.signal,
      });

      if (!res.ok) {
        setOcrMessage(`Vision 요청 실패: ${res.status}`);
        return;
      }

      const result = await res.json();
      const reliableExpiry = result.expiry_source === "label_linked" || result.expiry_source === "keyword_line";

      setForm((prev) => ({
        ...prev,
        name: result.name || "",
        expiry_date: result.expiry_date || "",
      }));

      if (result.fallback_to_manual) {
        setOcrMessage(mapOcrFailReason(result.fail_reason));
      } else if (result.expiry_date && !reliableExpiry) {
        setOcrMessage("유통기한을 자동 반영했지만 인식 신뢰도가 낮습니다. 사진과 일치하는지 꼭 확인해 주세요.");
      } else if (!result.expiry_date) {
        setOcrMessage("식재료명만 자동 반영했습니다. 유통기한을 찾지 못해 수동 입력이 필요합니다.");
      } else {
        setOcrMessage("Vision 인식 결과를 입력칸에 반영했습니다. 저장 전 확인해 주세요.");
      }
    } catch (err) {
      if (err?.name === "AbortError") {
        setOcrMessage("인식 시간이 너무 오래 걸려 중단했습니다. 이미지를 다시 시도하거나 수동 입력으로 진행해 주세요.");
      } else {
        setOcrMessage("백엔드 서버 연결에 실패했습니다. 서버 상태를 확인해 주세요.");
      }
    } finally {
      window.clearTimeout(timeoutId);
      setIsOcrLoading(false);
    }
  }

  async function submit(e) {
    e.preventDefault();
    const device_id = getOrCreateDeviceId();

    const payload = {
      ...form,
      device_id,
      qty: Number(form.qty),
    };

    const saved = await apiPost("/inventory", payload);
    setMessage(`저장 완료: ${saved.name} / 수량 ${saved.total_qty}`);
    setForm(initial);
  }

  return (
    <main className="shell">
      <section className="hero">
        <h1>식재료 등록</h1>
        <p>Vision 등록과 수동 입력을 모두 지원합니다. 현재 Vision은 준비중이며 수동 입력으로 바로 이어서 등록할 수 있습니다.</p>
        <nav className="nav">
          <Link href="/">대시보드</Link>
          <Link href="/inventory">재고 관리</Link>
        </nav>
      </section>

      <section className="grid">
        <article className="card card-half">
          <h3>Vision 등록</h3>
          <p className="fine">이미지를 선택한 뒤 인식 버튼을 눌러 주세요. 실제 Vision API 연동은 아직 적용하지 않았습니다.</p>
          <div className="vision-upload-grid">
          <div className="field vision-field">
            <label>이미지 파일 첨부</label>
            <input
              className="vision-file-input"
              type="file"
              accept="image/*"
              onChange={(e) => onVisionFileSelected(e.target.files?.[0] || null)}
            />
          </div>
          {isMobileDevice && (
            <div className="field vision-field">
              <label>카메라로 바로 촬영</label>
              <input
                className="vision-file-input"
                type="file"
                accept="image/*"
                capture="environment"
                onChange={(e) => onVisionFileSelected(e.target.files?.[0] || null)}
              />
            </div>
          )}
          </div>
          <button className="vision-submit" onClick={runMockOcr} disabled={isOcrLoading}>
            {isOcrLoading ? "인식 중..." : "Vision 인식 (준비중)"}
          </button>
          {visionFileName && <p className="fine">선택한 파일: {visionFileName}</p>}
          {ocrMessage && <p>{ocrMessage}</p>}
        </article>

        <article className="card card-half">
          <h3>수동 입력</h3>
          <form onSubmit={submit}>
            <div className="field">
              <label>식재료명</label>
              <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
            </div>
            <div className="field">
              <label>유통기한</label>
              <input
                type="date"
                value={form.expiry_date}
                onChange={(e) => setForm({ ...form, expiry_date: e.target.value })}
                required
              />
            </div>
            <div className="field">
              <label>수량</label>
              <input
                type="number"
                min="1"
                value={form.qty}
                onChange={(e) => setForm({ ...form, qty: e.target.value })}
                required
              />
            </div>
            <button className="primary" type="submit">
              저장
            </button>
          </form>
          {message && <p>{message}</p>}
        </article>
      </section>
    </main>
  );
}
