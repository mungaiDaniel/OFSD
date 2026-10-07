import {
  createContext,
  useContext,
  useReducer,
  useCallback,
  type ReactNode,
} from "react";
import type { UserRole } from "@/lib/types";
import {
  getAccessToken,
  getUserRole,
  getUserName,
  setTokens,
  clearTokens,
} from "@/lib/auth";
import { authService } from "@/services/authService";

// ── State ──

interface AuthState {
  role: UserRole | null;
  userName: string | null;
  isAuthenticated: boolean;
  loading: boolean;
  error: string | null;
}

// ── Actions ──

type AuthAction =
  | { type: "AUTH_START" }
  | { type: "AUTH_SUCCESS"; payload: { role: UserRole; userName?: string } }
  | { type: "AUTH_FAILURE"; payload: string }
  | { type: "LOGOUT" }
  | { type: "CLEAR_ERROR" }
  | { type: "AUTH_FINISH" };

// ── Reducer ──

function authReducer(state: AuthState, action: AuthAction): AuthState {
  switch (action.type) {
    case "AUTH_START":
      return { ...state, loading: true, error: null };
    case "AUTH_SUCCESS":
      return {
        ...state,
        loading: false,
        isAuthenticated: true,
        role: action.payload.role,
        userName: action.payload.userName ?? state.userName,
        error: null,
      };
    case "AUTH_FAILURE":
      return {
        ...state,
        loading: false,
        isAuthenticated: false,
        error: action.payload,
      };
    case "LOGOUT":
      return {
        ...state,
        role: null,
        userName: null,
        isAuthenticated: false,
        loading: false,
        error: null,
      };
    case "CLEAR_ERROR":
      return { ...state, error: null };
    case "AUTH_FINISH":
      return { ...state, loading: false };
    default:
      return state;
  }
}

// ── Context Type ──

interface AuthContextValue extends AuthState {
  login: (email: string, password: string) => Promise<boolean>;
  register: (
    name: string,
    email: string,
    password: string
  ) => Promise<boolean>;
  logout: () => void;
  clearError: () => void;
  isSuperAdmin: boolean;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

// ── Provider ──

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(authReducer, {
    role: getUserRole(),
    userName: getUserName(),
    isAuthenticated: !!getAccessToken(),
    loading: false,
    error: null,
  });

  const login = useCallback(async (email: string, password: string) => {
    dispatch({ type: "AUTH_START" });
    try {
      const res = await authService.login(email, password);
      // Try to extract name from response (backend may include it)
      const userName = (res as unknown as { name?: string }).name ?? undefined;
      setTokens(res.access_token, res.refresh_token, res.role, userName);
      dispatch({
        type: "AUTH_SUCCESS",
        payload: { role: res.role as UserRole, userName },
      });
      return true;
    } catch (err: unknown) {
      let message = "Login failed. Please check your credentials.";
      const status = (err as any)?.response?.status;
      const errResponse = (err as any)?.response?.data;
      if (status === 403) {
        message = "Account Pending Approval. Please contact the system administrator.";
      }
      if (errResponse?.message) {
        message = typeof errResponse.message === "string" 
          ? errResponse.message 
          : JSON.stringify(errResponse.message);
      } else if ((err as any)?.message) {
        message = (err as any).message;
      }
      dispatch({ type: "AUTH_FAILURE", payload: message });
      return false;
    }
  }, []);

  const register = useCallback(
    async (name: string, email: string, password: string) => {
      dispatch({ type: "AUTH_START" });
      try {
        await authService.register({
          name,
          email,
          password,
        });
        // Do not auto-login; let the email verification process take place.
        dispatch({ type: "AUTH_FINISH" });
        return true;
      } catch (err: unknown) {
        let message = "Registration failed.";
        const errResponse = (err as any)?.response?.data;
        if (errResponse?.message) {
          message = typeof errResponse.message === "string" 
            ? errResponse.message 
            : JSON.stringify(errResponse.message);
        } else if ((err as any)?.message) {
          message = (err as any).message;
        }
        dispatch({ type: "AUTH_FAILURE", payload: message });
        return false;
      }
    },
    [login]
  );

  const logout = useCallback(() => {
    clearTokens();
    dispatch({ type: "LOGOUT" });
  }, []);

  const clearError = useCallback(() => {
    dispatch({ type: "CLEAR_ERROR" });
  }, []);

  const value: AuthContextValue = {
    ...state,
    login,
    register,
    logout,
    clearError,
    isSuperAdmin: state.role === "super_admin",
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// ── Hook ──

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
