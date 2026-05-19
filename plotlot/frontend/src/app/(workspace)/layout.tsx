import { Suspense } from "react";
import { SidebarLayout } from "@/app/SidebarLayout";

export default function WorkspaceLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return <Suspense fallback={null}><SidebarLayout>{children}</SidebarLayout></Suspense>;
}
