import { createContext, useContext, useEffect, useState } from "react";
import { api } from "@/lib/api";

const AuthCtx = createContext(null);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const id = api.interceptors.response.use(
      (r) => r,
      (e) => {
        if (e?.response?.status === 401 && !e.config.url.includes("/auth/login")) {
          localStorage.removeItem("vb_token");
          setUser(null);
        }
        return Promise.reject(e);
      }
    );
    if (localStorage.getItem("vb_token")) {
      api.get("/auth/me").then((r) => setUser(r.data)).catch(() => {}).finally(() => setReady(true));
    } else {
      setReady(true);
    }
    return () => { api.interceptors.response.eject(id); };
  }, []);

  const login = async (email, password) => {
    const r = await api.post("/auth/login", { email, password });
    localStorage.setItem("vb_token", r.data.token);
    setUser(r.data.user);
    return r.data.user;
  };

  const register = async (body) => {
    const r = await api.post("/auth/register", body);
    localStorage.setItem("vb_token", r.data.token);
    setUser(r.data.user);
    return r.data.user;
  };

  const logout = () => {
    localStorage.removeItem("vb_token");
    setUser(null);
  };

  return <AuthCtx.Provider value={{ user, ready, login, register, logout }}>{children}</AuthCtx.Provider>;
};

export const useAuth = () => useContext(AuthCtx);
