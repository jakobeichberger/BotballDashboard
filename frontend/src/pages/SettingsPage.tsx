import { useQuery } from "@tanstack/react-query";
import { Routes, Route, NavLink } from "react-router-dom";
import { Settings, Users } from "lucide-react";
import { api } from "@/lib/api";
import clsx from "clsx";

function UsersSettings() {
  const { data: users, isLoading } = useQuery({
    queryKey: ["users"],
    queryFn: async () => {
      const { data } = await api.get("/auth/users");
      return data;
    },
  });

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold">Benutzer</h2>
        <button className="btn-primary text-sm">+ Benutzer anlegen</button>
      </div>
      {isLoading && <p className="text-gray-500 text-sm">Laden...</p>}
      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 dark:bg-gray-800">
            <tr>
              <th className="px-4 py-3 text-left font-medium">Name</th>
              <th className="px-4 py-3 text-left font-medium">E-Mail</th>
              <th className="px-4 py-3 text-left font-medium">Rollen</th>
              <th className="px-4 py-3 text-left font-medium">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y dark:divide-gray-800">
            {users?.map((user: any) => (
              <tr key={user.id}>
                <td className="px-4 py-3 font-medium">{user.display_name}</td>
                <td className="px-4 py-3 text-gray-500">{user.email}</td>
                <td className="px-4 py-3">
                  {user.roles.map((r: any) => (
                    <span key={r.id} className="badge-blue mr-1">{r.name}</span>
                  ))}
                </td>
                <td className="px-4 py-3">
                  <span className={user.is_active ? "badge-green" : "badge-gray"}>
                    {user.is_active ? "Aktiv" : "Inaktiv"}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function SettingsPage() {
  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-6 flex items-center gap-2">
        <Settings className="w-6 h-6" />
        Einstellungen
      </h1>

      <div className="flex gap-6">
        {/* Sidebar */}
        <aside className="w-48 shrink-0">
          <nav className="space-y-1">
            <NavLink
              to="/settings/users"
              className={({ isActive }) =>
                clsx(
                  "flex items-center gap-2 px-3 py-2 rounded-lg text-sm",
                  isActive
                    ? "bg-primary-50 text-primary-700 dark:bg-primary-900/30 dark:text-primary-300"
                    : "text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800"
                )
              }
            >
              <Users className="w-4 h-4" />
              Benutzer
            </NavLink>
          </nav>
        </aside>

        {/* Content */}
        <div className="flex-1">
          <Routes>
            <Route path="users" element={<UsersSettings />} />
          </Routes>
        </div>
      </div>
    </div>
  );
}
