import { useEffect, useState } from "react";
import { fetchArchive, type ArchiveManifest } from "../lib/archive";

export function useArchive(): ArchiveManifest | null {
  const [archive, setArchive] = useState<ArchiveManifest | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetchArchive(controller.signal)
      .then(setArchive)
      .catch(() => setArchive(null));
    return () => controller.abort();
  }, []);

  return archive;
}
