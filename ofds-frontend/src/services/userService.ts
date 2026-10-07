import api from "./api";
import { API } from "@/lib/constants";
import type { User } from "@/lib/types";

export const userService = {
  async getAll(): Promise<User[]> {
    const res = await api.get<User[] | [User[], number]>(API.USERS);
    const data = res.data;

    // Backend may return direct user array, or tuple [users, count] for pagination.
    if (Array.isArray(data)) {
      // If format is [users, count], first element is the array.
      if (data.length > 0 && Array.isArray(data[0]) && typeof data[1] === "number") {
        return data[0] as User[];
      }
      return data as User[];
    }

    return [];
  },

  async getById(id: number): Promise<User> {
    const res = await api.get<User>(API.USER_BY_ID(id));
    return res.data;
  },

  async approve(id: number): Promise<User> {
    const res = await api.patch<User>(API.APPROVE_USER(id));
    return res.data;
  },

  async setStatus(id: number, status: "pending" | "active"): Promise<User> {
    const res = await api.patch<User>(API.SET_USER_STATUS(id), { status });
    return res.data;
  },

  async setRole(id: number, role: "user" | "admin" | "super_admin"): Promise<User> {
    const res = await api.patch<User>(API.SET_USER_ROLE(id), { role });
    return res.data;
  },

  async resetPassword(id: number, password: string): Promise<void> {
    await api.patch(API.RESET_USER_PASSWORD(id), { password });
  },

  async delete(id: number): Promise<void> {
    await api.delete(API.USER_BY_ID(id));
  },
};
