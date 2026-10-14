import React, { useEffect, useState } from "react";
import { X, Lock } from "lucide-react";
import type { CoreFund, ProductType } from "@/lib/types";
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

export interface ShareClassFormValues {
  fund_id: number | "";
  class_name: string;
  class_code: string;
  currency: string;
  is_active: boolean;
}

interface ShareClassFormProps {
  /** "create" = the existing Add Share Class form; "edit" = same form, prefilled. */
  mode: "create" | "edit";
  product: ProductType;
  currencies: string[];
  initial?: Partial<ShareClassFormValues>;
  /** Create only: funds/shares to choose from (Add Share Class on the list page). */
  funds?: CoreFund[];
  submitting?: boolean;
  errors?: Record<string, string>;
  banner?: React.ReactNode;
  onSubmit: (values: ShareClassFormValues) => void;
  onCancel: () => void;
  /** Edit only: currency can't be changed (deposits/batches/valuations exist). */
  currencyLocked?: boolean;
  currencyLockReasons?: string[];
  /** Edit only: super_admin may unlock the currency through an explicit confirmation. */
  canOverrideCurrency?: boolean;
  onRequestCurrencyOverride?: () => void;
  /** Edit only: set once the override has been confirmed in the dialog. */
  currencyOverrideConfirmed?: boolean;
  openBatches?: string[];
}

/**
 * Add / Edit Share Class form (Task 12) — shared by FundListPage (create)
 * and FundDetailPage (edit) for both products.
 */
export function ShareClassForm({
  mode,
  product,
  currencies,
  initial,
  funds = [],
  submitting = false,
  errors = {},
  banner,
  onSubmit,
  onCancel,
  currencyLocked = false,
  currencyLockReasons = [],
  canOverrideCurrency = false,
  onRequestCurrencyOverride,
  currencyOverrideConfirmed = false,
  openBatches = [],
}: ShareClassFormProps) {
  const isEdit = mode === "edit";
  const noun = product === "SHARES" ? "share" : "fund";
  const Noun = product === "SHARES" ? "Share" : "Fund";
  const empty: ShareClassFormValues = {
    fund_id: "",
    class_name: "",
    class_code: "",
    currency: currencies[0] ?? "",
    is_active: true,
  };
  const [values, setValues] = useState<ShareClassFormValues>({ ...empty, ...initial });

  useEffect(() => {
    setValues({ ...empty, ...initial });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(initial ?? {})]);

  const set = <K extends keyof ShareClassFormValues>(k: K, v: ShareClassFormValues[K]) =>
    setValues((prev) => ({ ...prev, [k]: v }));

  const currencyEditable = !isEdit || !currencyLocked || currencyOverrideConfirmed;
  // The current currency must always be selectable, even if it's outside the
  // product allow-list (legacy rows) — otherwise the select would silently change it.
  const currencyOptions = Array.from(new Set([...(initial?.currency ? [initial.currency] : []), ...currencies]));

  const invalid =
    (!isEdit && !values.fund_id) || !values.class_name.trim() || !values.class_code.trim() || !values.currency;
  const disabled = submitting || invalid;

  const submit = () => {
    if (invalid) return;
    onSubmit({
      ...values,
      class_name: values.class_name.trim(),
      class_code: values.class_code.trim().toUpperCase(),
    });
  };

  return (
    <div className="card shadow mb-4" style={formCardStyle} data-testid={`share-class-form-${mode}`}>
      <div className="card-body">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px" }}>
          <h5 className="fw-bold mb-0" style={{ fontSize: "14px", color: "var(--color-text-primary)" }}>
            {isEdit ? "Edit Share Class" : "Add Share Class"}
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
          {!isEdit && (
            <div className="col-md-6">
              <label style={labelStyle}>{Noun} *</label>
              <select
                value={values.fund_id}
                onChange={(e) => set("fund_id", e.target.value ? Number(e.target.value) : "")}
                style={selectStyle}
                onFocus={handleFocus}
                onBlur={handleBlur}
              >
                <option value="">Select a {noun}...</option>
                {funds.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.fund_name}
                  </option>
                ))}
              </select>
            </div>
          )}
          <div className="col-md-6">
            <label style={labelStyle} htmlFor={`class-name-${mode}`}>Class Name *</label>
            <input
              id={`class-name-${mode}`}
              value={values.class_name}
              onChange={(e) => set("class_name", e.target.value)}
              placeholder="e.g. Class I Participating Shares"
              style={withError(inputStyle, !!errors.class_name)}
              onFocus={handleFocus}
              onBlur={handleBlur}
              maxLength={100}
              autoFocus
            />
            {errors.class_name && <div style={errorTextStyle}>{errors.class_name}</div>}
          </div>
          {isEdit && (
            <div className="col-md-6">
              <label style={labelStyle} htmlFor="class-code-edit">Class Code *</label>
              <input
                id="class-code-edit"
                value={values.class_code}
                onChange={(e) => set("class_code", e.target.value.toUpperCase())}
                placeholder="e.g. KES_I"
                style={withError(inputStyle, !!errors.class_code)}
                onFocus={handleFocus}
                onBlur={handleBlur}
                maxLength={20}
              />
              {errors.class_code && <div style={errorTextStyle}>{errors.class_code}</div>}
            </div>
          )}
        </div>

        <div className="row g-3 mb-3">
          {!isEdit && (
            <div className="col-md-6">
              <label style={labelStyle}>Class Code *</label>
              <input
                value={values.class_code}
                onChange={(e) => set("class_code", e.target.value.toUpperCase())}
                placeholder="e.g. KES_I"
                style={withError(inputStyle, !!errors.class_code)}
                onFocus={handleFocus}
                onBlur={handleBlur}
                maxLength={10}
              />
              {errors.class_code && <div style={errorTextStyle}>{errors.class_code}</div>}
            </div>
          )}
          <div className="col-md-6">
            <label style={labelStyle} htmlFor={`class-currency-${mode}`}>Currency *</label>
            {currencyEditable ? (
              <select
                id={`class-currency-${mode}`}
                value={values.currency}
                onChange={(e) => set("currency", e.target.value)}
                style={withError(selectStyle, !!errors.currency)}
                onFocus={handleFocus}
                onBlur={handleBlur}
              >
                {currencyOptions.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            ) : (
              <div style={{ position: "relative" }}>
                <input
                  id={`class-currency-${mode}`}
                  value={values.currency}
                  readOnly
                  aria-readonly
                  style={readOnlyStyle}
                />
                <Lock
                  size={13}
                  style={{ position: "absolute", right: 12, top: "50%", transform: "translateY(-50%)", color: "#94A3B8" }}
                />
              </div>
            )}
            {errors.currency && <div style={errorTextStyle}>{errors.currency}</div>}
            {isEdit && currencyLocked && !currencyOverrideConfirmed && (
              <div style={hintTextStyle}>
                Currency is locked because this has deposits/valuations
                {currencyLockReasons.length ? ` (${currencyLockReasons.join(", ")})` : ""}.
                {canOverrideCurrency && onRequestCurrencyOverride && (
                  <>
                    {" "}
                    <button
                      type="button"
                      onClick={onRequestCurrencyOverride}
                      style={{
                        background: "none",
                        border: "none",
                        padding: 0,
                        color: "#fbbf24",
                        fontSize: "11px",
                        textDecoration: "underline",
                        cursor: "pointer",
                      }}
                    >
                      Override (super admin)
                    </button>
                  </>
                )}
              </div>
            )}
            {isEdit && currencyLocked && currencyOverrideConfirmed && (
              <div style={{ ...hintTextStyle, color: "#fbbf24" }}>
                Override confirmed — existing figures will NOT be converted.
              </div>
            )}
          </div>
          {isEdit && (
            <div className="col-md-6">
              <label style={labelStyle} htmlFor="class-status-edit">Status</label>
              <select
                id="class-status-edit"
                value={values.is_active ? "active" : "inactive"}
                onChange={(e) => set("is_active", e.target.value === "active")}
                style={withError(selectStyle, !!errors.is_active)}
                onFocus={handleFocus}
                onBlur={handleBlur}
              >
                <option value="active">Active</option>
                <option value="inactive">Inactive</option>
              </select>
              {errors.is_active && <div style={errorTextStyle}>{errors.is_active}</div>}
              {!errors.is_active && !values.is_active && openBatches.length > 0 && (
                <div style={errorTextStyle}>
                  Can't deactivate while these batches are open: {openBatches.join(", ")}
                </div>
              )}
            </div>
          )}
        </div>

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
            {isEdit ? (submitting ? "Saving..." : "Save changes") : submitting ? "Adding..." : "Add Share Class"}
          </button>
        </div>
      </div>
    </div>
  );
}
