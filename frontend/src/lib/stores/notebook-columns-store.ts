import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface NotebookColumnsState {
  sourcesCollapsed: boolean
  notesCollapsed: boolean
  marketCollapsed: boolean
  toggleSources: () => void
  toggleNotes: () => void
  toggleMarket: () => void
  setSources: (collapsed: boolean) => void
  setNotes: (collapsed: boolean) => void
  setMarket: (collapsed: boolean) => void
}

export const useNotebookColumnsStore = create<NotebookColumnsState>()(
  persist(
    (set) => ({
      sourcesCollapsed: false,
      notesCollapsed: false,
      marketCollapsed: false,
      toggleSources: () => set((state) => ({ sourcesCollapsed: !state.sourcesCollapsed })),
      toggleNotes: () => set((state) => ({ notesCollapsed: !state.notesCollapsed })),
      toggleMarket: () => set((state) => ({ marketCollapsed: !state.marketCollapsed })),
      setSources: (collapsed) => set({ sourcesCollapsed: collapsed }),
      setNotes: (collapsed) => set({ notesCollapsed: collapsed }),
      setMarket: (collapsed) => set({ marketCollapsed: collapsed }),
    }),
    {
      name: 'notebook-columns-storage',
    }
  )
)
