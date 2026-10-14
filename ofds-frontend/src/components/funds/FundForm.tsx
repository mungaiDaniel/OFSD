import React, { useEffect, useState } from "react";
import { X } from "lucide-react";
import type { ProductType } from "@/lib/types";
import {
  inputStyle,
  selectStyle,
  readOnlyStyle,
  labelStyle,
  errorTextStyle,
  hintTextStyle,
  formCardStyle,
  cancelButtonStyle,
  primaryButtonStyle,
  withError,
  handleFocus,
  handleBlur,
  hoverCancel,
} from "./formStyles";

export interface FundFormValues {
  fund_name: string;
  fund_code: string;
  description: string;
  is_active: boolean;
}

interface FundFormProps {
  /** "create" = the existing New fund/share form; "edit" = same form, prefilled. */
  mode: "create" | "edit";
  product: ProductType;
  initial?: Partial<FundFormValues>;
  submitting?: boolean;
  /** Server-side field errors, keyed by field name (fund_name, fund_code, …). */
  errors?: Record<string, string>;
  /** Form-level message (e.g. a version conflict), rendered above the buttons. */
  banner?: React.ReactNode;
  onSubmit: (values: FundFormValues) => void;
  onCancel: () => void;
  /** Edit only: currencies of this fund's share classes (read-only here). */
  classCurrencies?: string[];
  /** Edit only: name can't change (hash-chained ledger history). */
  renameLocked?: boolean;
  /** Edit only: open batches that block deactivation. */
  openBatches?: string[];
}

const EMPTY: FundFormValues = { fund_name: "", fund_code: "", description: "", is_active: true };

/**
 * Create / Edit Fund-or-Share form (Task 12). Used by FundListPage (create)
 * and FundDetailPage (edit) for BOTH products — wording and placeholders
 * follow `product`. Product itself is never editable.
 */
export function FundForm({
  mode,
  product,
  initial,
  submitting = false,
  errors = {},
  banner,
  onSubmit,
  onCancel,
  classCurrencies = [],
  renameLocked = false,
  openBatches = [],
}: FundFormProps) {
  const isShares = product === "SHARES";
  const Noun = isShares ? "Share" : "Fund";
  const isEdit = mode === "edit";

  const [values, setValues] = useState<FundFormValues>({ ...EMPTY, ...initial });
  const [touched, setTouched] = useState(false);

  // Re-seed when the record is (re)loaded, e.g. after "Reload latest values".
  useEffect(() => {
    setValues({ ...EMPTY, ...initial });
    setTouched(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(initial ?? {})]);

  const set = <K extends keyof FundFormValues>(k: K, v: FundFormValues[K]) =>
    setValues((prev) => ({ ...prev, [k]: v }));

  // Same client-side rules as creation: name and code required.
  const localErrors: Record<string, string> = {};
  if (touched && !values.fund_name.trim()) localErrors.fund_name = `${Noun} name is required`;
  if (touched && !values.fund_code.trim()) localErrors.fund_code = `${Noun} code is required`;
  const err = (k: string) => localErrors[k] ?? errors[k];

  const invalid = !values.fund_name.trim() || !values.fund_code.trim();
  const disabled = submitting || invalid;

  const submit = () => {
    setTouched(true);
    if (invalid) return;
    onSubmit({
      ...values,
      fund_name: values.fund_name.trim(),
      fund_code: values.fund_code.trim().toUpperCase(),
      description: values.description.trim(),
    });
  };

  const title = isEdit ? `Edit ${Noun}` : `Create New ${Noun}`;
  const submitLabel = isEdit
    ? submitting ? "Saving..." : "Save changes"
    : submitting ? "Creating..." : `Create ${Noun}`;

  return (
    <div className="card shadow mb-4" style={formCardStyle} data-testid={`fund-form-${mode}`}>
      <div className="card-body">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px" }}>
          <h5 className="fw-bold mb-0" style={{ fontSize: "14px", color: "var(--color-text-primary)" }}>
            {title}
          </h5>
          <button
            type="button"
            aria-label="Close"
            onClick={onCancel}
            style={{ background: "none", border: "none", color: "var(--color-text-tertiary)", cursor: "pointer" }}
          >
            <X size={18} />
          </button>
        </div>

        <div className="row g-3 mb-3">
          <div className="col-md-6">
            <label style={labelStyle} htmlFor={`fund-name-${mode}`}>{Noun} Name *</label>
            <input
              id={`fund-name-${mode}`}
              value={values.fund_name}
              onChange={(e) => set("fund_name", e.target.value)}
              placeholder={isShares ? "e.g. Dangote Petroleum Refinery" : "e.g. Axiom"}
              style={renameLocked ? readOnlyStyle : withError(inputStyle, !!err("fund_name"))}
              onFocus={handleFocus}
              onBlur={handleBlur}
              readOnly={renameLocked}
              maxLength={100}
              autoFocus={!isEdit}
            />
            {err("fund_name") && <div style={errorTextStyle}>{err("fund_name")}</div>}
            {renameLocked && !err("fund_name") && (
              <div style={hintTextStyle}>
                Name is locked because this {Noun.toLowerCase()} has committed ledger history.
              </div>
            )}
          </div>
          <div className="col-md-6">
            <label style={labelStyle} htmlFor={`fund-code-${mode}`}>{Noun} Code *</label>
            <input
              id={`fund-code-${mode}`}
              value={values.fund_code}
              onChange={(e) => set("fund_code", e.target.value.toUpperCase())}
              placeholder={isShares ? "e.g. DPRP" : "e.g. AXM"}
              style={withError(inputStyle, !!err("fund_code"))}
              onFocus={handleFocus}
              onBlur={handleBlur}
              maxLength={10}
            />
            {err("fund_code") && <div style={errorTextStyle}>{err("fund_code")}</div>}
          </div>
        </div>

        <div className="row g-3 mb-3">
          <div className="col-12">
            <label style={labelStyle} htmlFor={`fund-desc-${mode}`}>Description</label>
            <textarea
              id={`fund-desc-${mode}`}
              value={values.description}
              onChange={(e) => set("description", e.target.value)}
              placeholder="Optional"
              rows={2}
              maxLength={1000}
              style={{ ...withError(inputStyle, !!err("description")), resize: "vertical" }}
              onFocus={handleFocus}
              onBlur={handleBlur}
            />
            {err("description") && <div style={errorTextStyle}>{err("description")}</div>}
          </div>
        </div>

        {isEdit && (
          <div className="row g-3 mb-3">
            <div className="col-md-4">
              <label style={labelStyle} htmlFor="fund-status-edit">Status</label>
              <select
                id="fund-status-edit"
                value={values.is_active ? "active" : "inactive"}
                onChange={(e) => set("is_active", e.target.value === "active")}
                style={withError(selectStyle, !!err("is_active"))}
                onFocus={handleFocus}
                onBlur={handleBlur}
              >
                <option value="active">Active</option>
                <option value="inactive">Inactive</option>
              </select>
              {err("is_active") && <div style={errorTextStyle}>{err("is_active")}</div>}
              {!err("is_active") && !values.is_active && openBatches.length > 0 && (
                <div style={errorTextStyle}>
                  Can't deactivate while these batches are open: {openBatches.join(", ")}
                </div>
              )}
            </div>
            <div className="col-md-4">
              <label style={labelStyle}>Currency</label>
              <input
                value={classCurrencies.length ? classCurrencies.join(", ") : "—"}
                readOnly
                aria-readonly
                style={readOnlyStyle}
                title="Currency is set on each share class"
              />
              <div style={hintTextStyle}>Set per share class (edit it on the class below).</div>
            </div>
            <div className="col-md-4">
              <label style={labelStyle}>Product</label>
              <input value={isShares ? "Shares" : "Funds"} readOnly aria-readonly style={readOnlyStyle} />
              <div style={hintTextStyle}>Product can't be changed.</div>
            </div>
          </div>
        )}

        {banner}

        <div
          style={{
            display: "flex",
            gap: "12px",
            justifyContent: "flex-end",
            marginTop: "24px",
            paddingTop: "16px",
            borderTop: "1px solid rgba(255,255,255,0.07)",
          }}
        >
          <button
            type="button"
            onClick={onCancel}
            style={cancelButtonStyle}
            onMouseEnter={(e) => hoverCancel(e, true)}
            onMouseLeave={(e) => hoverCancel(e, false)}
          >
            Cancel
          </button>
          <button type="button" onClick={submit} disabled={disabled} style={primaryButtonStyle(disabled)}>
            {submitLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
