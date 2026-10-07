import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useAuth } from "@/context/AuthContext";
import { ROUTES } from "@/lib/constants";

const registerSchema = z
  .object({
    name: z
      .string()
      .min(3, "Full name is required")
      .regex(
        /^[a-zA-Z\s\-']+$/,
        "Name can only contain letters, spaces, hyphens, and apostrophes"
      )
      .refine(
        (val) => val.trim().split(/\s+/).length >= 2,
        "Full name must contain at least two words"
      ),
    email: z.string().email("Valid email is required"),
    password: z
      .string()
      .min(8, "At least 8 characters")
      .regex(/[A-Z]/, "Must contain an uppercase letter")
      .regex(/[a-z]/, "Must contain a lowercase letter")
      .regex(/[0-9]/, "Must contain a number")
      .regex(/[@$!%*?&]/, "Must contain a special character (@$!%*?&)"),
    confirmPassword: z.string(),
  })
  .refine((data) => data.password === data.confirmPassword, {
    message: "Passwords don't match",
    path: ["confirmPassword"],
  });

type RegisterForm = z.infer<typeof registerSchema>;

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "10px 14px",
  background: "rgba(255, 255, 255, 0.04)",
  border: "1px solid rgba(255, 255, 255, 0.12)",
  borderRadius: "8px",
  fontSize: "13px",
  color: "var(--color-text-primary)",
  outline: "none",
  boxSizing: "border-box",
};

const labelStyle: React.CSSProperties = {
  display: "block",
  fontSize: "11px",
  fontWeight: 600,
  color: "var(--color-text-tertiary)",
  textTransform: "uppercase",
  letterSpacing: "0.06em",
  marginBottom: "6px",
};

export default function RegisterPage() {
  const { register: registerUser, loading, error, clearError } = useAuth();
  const navigate = useNavigate();
  const [showPassword, setShowPassword] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<RegisterForm>({
    resolver: zodResolver(registerSchema),
  });

  const onSubmit = async (data: RegisterForm) => {
    clearError();
    const success = await registerUser(data.name, data.email, data.password);
    if (success) {
      navigate(ROUTES.LOGIN, { replace: true, state: { email: data.email } });
    }
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "24px",
        background: "var(--color-bg-base)",
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: "420px",
          background: "rgba(16, 24, 45, 0.72)",
          backdropFilter: "blur(20px) saturate(150%)",
          WebkitBackdropFilter: "blur(20px) saturate(150%)",
          border: "1px solid rgba(255, 255, 255, 0.07)",
          borderRadius: "20px",
          boxShadow: "rgba(0, 0, 0, 0.4) 0px 8px 40px",
          padding: "36px 32px",
          margin: "24px 0",
        }}
      >
        <div style={{ display: "flex", justifyContent: "center", marginBottom: "24px" }}>
          <img
            src="/logo.webp"
            alt="AIB AXYS Africa"
            style={{ height: "36px", objectFit: "contain" }}
          />
        </div>

        <h1
          style={{
            fontSize: "20px",
            fontWeight: 700,
            textAlign: "center",
            color: "var(--color-text-primary)",
            letterSpacing: "-0.02em",
            marginBottom: "4px",
          }}
        >
          Create account
        </h1>
        <p
          style={{
            fontSize: "13px",
            textAlign: "center",
            color: "var(--color-text-secondary)",
            marginBottom: "28px",
          }}
        >
          Request access to OFSD
        </p>

        {error && (
          <div
            style={{
              background: "var(--color-destructive-bg)",
              border: "1px solid var(--color-destructive)",
              borderRadius: "8px",
              padding: "10px 14px",
              marginBottom: "16px",
              fontSize: "13px",
              color: "var(--color-destructive)",
            }}
          >
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit(onSubmit)}>
          <div style={{ marginBottom: "14px" }}>
            <label style={labelStyle}>Full name</label>
            <input
              {...register("name")}
              style={inputStyle}
              placeholder="Jane Doe"
              autoComplete="name"
              autoFocus
            />
            {errors.name && (
              <p className="text-xs mt-1" style={{ color: "var(--color-destructive)" }}>{errors.name.message}</p>
            )}
          </div>

          <div style={{ marginBottom: "14px" }}>
            <label style={labelStyle}>Email</label>
            <input
              type="email"
              {...register("email")}
              style={inputStyle}
              placeholder="you@company.com"
              autoComplete="email"
            />
            {errors.email && (
              <p className="text-xs mt-1" style={{ color: "var(--color-destructive)" }}>{errors.email.message}</p>
            )}
          </div>

          <div style={{ marginBottom: "14px" }}>
            <label style={labelStyle}>Password</label>
            <div style={{ position: "relative" }}>
              <input
                type={showPassword ? "text" : "password"}
                {...register("password")}
                style={inputStyle}
                placeholder="Min 8 chars, upper, lower, number, symbol"
                autoComplete="new-password"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                tabIndex={-1}
                style={{
                  position: "absolute",
                  right: "12px",
                  top: "50%",
                  transform: "translateY(-50%)",
                  background: "none",
                  border: "none",
                  fontSize: "11px",
                  color: "var(--color-text-tertiary)",
                  cursor: "pointer",
                }}
              >
                {showPassword ? "Hide" : "Show"}
              </button>
            </div>
            {errors.password && (
              <p className="text-xs mt-1" style={{ color: "var(--color-destructive)" }}>{errors.password.message}</p>
            )}
          </div>

          <div style={{ marginBottom: "24px" }}>
            <label style={labelStyle}>Confirm password</label>
            <input
              type="password"
              {...register("confirmPassword")}
              style={inputStyle}
              placeholder="Re-enter password"
              autoComplete="new-password"
            />
            {errors.confirmPassword && (
              <p className="text-xs mt-1" style={{ color: "var(--color-destructive)" }}>{errors.confirmPassword.message}</p>
            )}
          </div>

          <button
            type="submit"
            disabled={loading}
            style={{
              width: "100%",
              padding: "11px",
              borderRadius: "10px",
              background: "rgb(26, 69, 255)",
              border: "none",
              color: "rgb(255, 255, 255)",
              fontSize: "13px",
              fontWeight: 600,
              cursor: loading ? "not-allowed" : "pointer",
              opacity: loading ? 0.7 : 1,
              boxShadow: "rgba(26, 69, 255, 0.35) 0px 0px 20px",
            }}
          >
            {loading ? "Creating account..." : "Create account"}
          </button>
        </form>

        <p
          style={{
            fontSize: "12px",
            textAlign: "center",
            color: "var(--color-text-tertiary)",
            marginTop: "20px",
            marginBottom: 0,
          }}
        >
          Already have an account?{" "}
          <Link
            to={ROUTES.LOGIN}
            style={{ color: "rgb(96, 165, 250)", textDecoration: "none", fontWeight: 500 }}
          >
            Sign in
          </Link>
        </p>

        <div style={{ textAlign: "center", marginTop: "10px" }}>
          <Link
            to={ROUTES.LANDING}
            style={{
              color: "var(--color-text-tertiary)",
              textDecoration: "none",
              fontSize: "12px",
            }}
          >
            Back to landing page
          </Link>
        </div>
      </div>
    </div>
  );
}
