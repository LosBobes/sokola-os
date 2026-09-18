import { useEffect, useMemo, useRef } from "react";
import qrcode from "qrcode-generator";
import { api } from "../api/client";
import type { PaymentSlip } from "../api/types";
import { useAsync } from "../hooks/useAsync";
import { formatDate } from "../lib/format";
import { formatAmount } from "../lib/money";
import { InlineNotice, LoadingState, SystemState } from "./ui";
import "./payment-slip.css";

/*
 * Uplatnica with an NBS IPS QR.
 *
 * WHAT THIS IS: an aid for filling in a payment order. Scanning the code fills
 * the payer's own banking app with the school's account, the amount and the
 * reference number, so nobody retypes an 18-digit account from a screenshot.
 *
 * WHAT THIS IS NOT: a payment. The money moves directly from the payer's bank
 * account to the school's, through their bank. SOKOLA OS is not in that path,
 * is never told the transfer happened, and never settles a charge by itself ,
 * an authorised person at the school confirms the payment after checking the
 * bank account. The dialog says all of this on screen, because a QR code next
 * to an amount looks exactly like a "pay now" button and would otherwise be
 * read as one.
 */

/** Error-correction level M: readable after normal print/screen wear. */
const QR_ERROR_CORRECTION = "M";
/** 0 = pick the smallest version that fits the payload. */
const QR_TYPE_AUTO = 0;

/**
 * Render the payload as an inline SVG.
 *
 * SVG rather than a canvas or a data-URL image: it stays crisp when the slip
 * is printed, which is the whole point of a payment slip, and it needs no
 * layout pass to be measured.
 */
function QrSvg({ payload, title }: { payload: string; title: string }) {
  const path = useMemo(() => {
    const qr = qrcode(QR_TYPE_AUTO, QR_ERROR_CORRECTION);
    qr.addData(payload);
    qr.make();
    const count = qr.getModuleCount();
    // One <path> of 1x1 squares beats thousands of <rect> nodes to parse.
    const parts: string[] = [];
    for (let row = 0; row < count; row++) {
      for (let col = 0; col < count; col++) {
        if (qr.isDark(row, col)) parts.push(`M${col} ${row}h1v1h-1z`);
      }
    }
    return { d: parts.join(""), count };
  }, [payload]);

  return (
    <svg
      className="slip-qr"
      viewBox={`-1 -1 ${path.count + 2} ${path.count + 2}`}
      role="img"
      aria-label={title}
      shapeRendering="crispEdges"
      data-cy="payment-slip-qr"
    >
      {/* The quiet zone is part of the spec; without it scanners miss the code. */}
      <rect x={-1} y={-1} width={path.count + 2} height={path.count + 2} fill="#ffffff" />
      <path d={path.d} fill="#000000" />
    </svg>
  );
}

function SlipRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="slip-row">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

export function PaymentSlipDialog({
  chargeId,
  onClose,
}: {
  chargeId: string;
  onClose: () => void;
}) {
  const slip = useAsync(
    () => api.get<PaymentSlip>(`/charges/${chargeId}/payment-slip`),
    [chargeId],
  );

  const dialogRef = useRef<HTMLDialogElement>(null);
  const restoreTo = useRef<Element | null>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog || dialog.open) return;
    restoreTo.current = document.activeElement;
    dialog.showModal();
    return () => {
      if (dialog.open) dialog.close();
      (restoreTo.current as HTMLElement | null)?.focus?.();
    };
  }, []);

  return (
    <dialog
      ref={dialogRef}
      className="card slip-dialog"
      onCancel={onClose}
      onClick={(e) => {
        if (e.target === dialogRef.current) onClose();
      }}
      data-cy="payment-slip-dialog"
    >
      <h2>Uplatnica</h2>
      <InlineNotice tone="info">
        QR kod služi samo kao pomoć pri popunjavanju naloga za uplatu. Novac se prenosi
        direktno sa računa uplatioca na račun škole. Uplatu ručno potvrđuje ovlašćena osoba
        škole, nakon provere bankovnog računa.
      </InlineNotice>

      {slip.loading ? <LoadingState label="Priprema uplatnice…" /> : null}
      {slip.error ? <SystemState error={slip.error} /> : null}

      {slip.data ? (
        <div className="slip">
          <QrSvg payload={slip.data.ips_qr_payload} title="NBS IPS QR kod za uplatu" />
          <dl className="slip-facts">
            <SlipRow label="Primalac" value={slip.data.payee_name} />
            {slip.data.payee_address || slip.data.payee_city ? (
              <SlipRow
                label="Adresa primaoca"
                value={[slip.data.payee_address, slip.data.payee_city]
                  .filter(Boolean)
                  .join(", ")}
              />
            ) : null}
            <SlipRow label="Račun primaoca" value={slip.data.account_number} />
            <SlipRow label="Uplatilac" value={slip.data.payer_name || "-"} />
            <SlipRow
              label="Iznos"
              value={formatAmount(slip.data.amount, slip.data.currency)}
            />
            <SlipRow label="Svrha uplate" value={slip.data.purpose} />
            <SlipRow label="Šifra plaćanja" value={slip.data.payment_code} />
            <SlipRow label="Poziv na broj" value={slip.data.reference_number} />
            {slip.data.due_date ? (
              <SlipRow label="Datum dospeća" value={formatDate(slip.data.due_date)} />
            ) : null}
          </dl>
        </div>
      ) : null}

      <div className="slip-actions">
        <button type="button" className="btn btn--primary" onClick={onClose} data-cy="payment-slip-close">
          Zatvori
        </button>
      </div>
    </dialog>
  );
}
