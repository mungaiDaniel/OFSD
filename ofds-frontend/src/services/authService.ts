import api from "./api";
import { API } from "@/lib/constants";
import type { LoginResponse, RegisterRequest, ApiResponse, User } from "@/lib/types";

export const authService = {
  async login(email: string, password: string): Promise<LoginResponse> {
    const res = await api.post<{ value: LoginResponse }>(API.LOGIN, { email, password });
    return res.data.value;
  },

  async register(data: RegisterRequest): Promise<ApiResponse<User>> {
    const res = await api.post<ApiResponse<User>>(API.REGISTER, data);
    return res.data;
  },
};
