import { useState } from "react";
import { useNavigate, useLocation, Link } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useAuth } from "@/context/AuthContext";
import { ROUTES } from "@/lib/constants";

const loginSchema = z.object({
  email: z.string().email("Valid email is required"),
  password: z.string().min(6, "Password must be at least 6 characters"),
});

type LoginForm = z.infer<typeof loginSchema>;

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

export default function LoginPage() {
  const { login, loading, error, clearError } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [showPassword, setShowPassword] = useState(false);

  const from = (location.state as { from?: { pathname: string } })?.from?.pathname || "/dashboard";
  const stateEmail = (location.state as { email?: string })?.email || "";

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginForm>({
    resolver: zodResolver(loginSchema),
    defaultValues: {
      email: stateEmail,
    },
  });

  const onSubmit = async (data: LoginForm) => {
    clearError();
    const success = await login(data.email, data.password);
    if (success) {
      navigate(from, { replace: true });
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
        }}
      >
        {/* Logo */}
        <div style={{ display: "flex", justifyContent: "center", marginBottom: "24px" }}>
          <img
            src="/axys-logo.webp"
            alt="AXYS Investment Bank"
            style={{ height: "48px", objectFit: "contain" }}
          />
        </div>

        {/* Title */}
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
          Sign in to OFSD
        </h1>
        <p
          style={{
            fontSize: "13px",
            textAlign: "center",
            color: "var(--color-text-secondary)",
            marginBottom: "28px",
          }}
        >
          Offshore Fund System &amp; Distribution
        </p>

        {/* Error message */}
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

        {/* Form */}
        <form onSubmit={handleSubmit(onSubmit)}>
          {/* Email */}
          <div style={{ marginBottom: "16px" }}>
            <label style={labelStyle}>Email</label>
            <input
              type="email"
              {...register("email")}
              style={inputStyle}
              placeholder="you@company.com"
              autoComplete="email"
              autoFocus
            />
            {errors.email && (
              <p className="text-xs mt-1" style={{ color: "var(--color-destructive)" }}>
                {errors.email.message}
              </p>
            )}
          </div>

          {/* Password */}
          <div style={{ marginBottom: "24px" }}>
            <label style={labelStyle}>Password</label>
            <div style={{ position: "relative" }}>
              <input
                type={showPassword ? "text" : "password"}
                {...register("password")}
                style={inputStyle}
                placeholder="Password"
                autoComplete="current-password"
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
              <p className="text-xs mt-1" style={{ color: "var(--color-destructive)" }}>
                {errors.password.message}
              </p>
            )}
          </div>

          {/* Submit */}
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
            {loading ? "Signing in..." : "Sign in"}
          </button>
        </form>

        {/* Register link */}
        <p
          style={{
            fontSize: "12px",
            textAlign: "center",
            color: "var(--color-text-tertiary)",
            marginTop: "20px",
            marginBottom: 0,
          }}
        >
          Don't have an account?{" "}
          <Link
            to={ROUTES.REGISTER}
            style={{ color: "rgb(96, 165, 250)", textDecoration: "none", fontWeight: 500 }}
          >
            Register
          </Link>
        </p>

        {/* Back to landing page */}
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
