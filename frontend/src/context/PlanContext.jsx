import { createContext, useContext, useEffect, useRef, useState } from 'react'
import { readSession, writeSession } from '../utils/storage'

const PlanContext = createContext(null)
// IDs are scoped to the authenticated subject; a guest request survives sign-in.
export function PlanProvider({ owner, children }) {
  const storageKey = `ecoroute:active:${owner || 'guest'}`
  const [active, setActive] = useState(() => ({ owner, id: owner ? readSession(storageKey) || '' : '' }))
  const previousOwner = useRef(owner)
  const [requestText, setRequestText] = useState('')
  const [draft, setDraft] = useState(null)
  useEffect(() => {
    setActive({ owner, id: owner ? readSession(storageKey) || '' : '' })
    if (previousOwner.current && previousOwner.current !== owner) { setDraft(null); setRequestText('') }
    previousOwner.current = owner
  }, [owner, storageKey])
  const activeId = active.owner === owner ? active.id : owner ? readSession(storageKey) || '' : ''
  const setActiveId = id => { setActive({ owner, id }); if (owner) writeSession(storageKey, id || null) }
  return <PlanContext.Provider value={{ activeId, setActiveId, requestText, setRequestText, draft, setDraft }}>{children}</PlanContext.Provider>
}
export const usePlan = () => useContext(PlanContext)
