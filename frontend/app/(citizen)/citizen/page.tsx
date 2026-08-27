import { redirect } from "next/navigation";

export default function CitizenIndex() {
  redirect("/citizen/health-record");
}
