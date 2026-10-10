import { useState } from 'react'
import { createPreference, updatePreference } from '../../api/preferences'
import Button from '../ui/Button'
import Input from '../ui/Input'
import ErrorMessage from '../ui/ErrorMessage'

export default function PreferenceEditor({ initial, onSaved, onCancel, signalRef }) {
  const [key, setKey] = useState(initial?.key || '')
  const [value, setValue] = useState(JSON.stringify(initial?.value || {}, null, 2))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const save = async event => {
    event.preventDefault(); setError(null); setBusy(true)
    signalRef.current = new AbortController()
    try {
      if (!key.trim()) throw new Error('Enter a preference key.')
      if (key.trim() === 'travel_mode') throw new Error('Use the travel mode selector to set this preference.')
      let parsed
      try { parsed = JSON.parse(value) } catch { throw new Error('Enter a valid JSON object for this preference.') }
      if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') throw new Error('The value must be a JSON object.')
      const result = initial ? await updatePreference(key, parsed, signalRef.current.signal) : await createPreference(key.trim(), parsed, signalRef.current.signal)
      onSaved(result)
    } catch (err) { if (err.name !== 'AbortError') setError(err) }
    finally { setBusy(false) }
  }
  return <form onSubmit={save} className="grid gap-4">
    <Input label="Preference key" required disabled={busy} maxLength={128} readOnly={Boolean(initial)} value={key} onChange={e => setKey(e.target.value)} />
    <label className="field"><span>Value (JSON object)</span><textarea disabled={busy} rows={5} maxLength={10000} value={value} onChange={e => setValue(e.target.value)} required className="font-mono text-xs" /></label>
    <p className="text-xs leading-5 text-neutral-500">Custom preferences are stored by the API. Only travel_mode currently changes travel calculations.</p>
    <ErrorMessage error={error} /><div className="flex flex-wrap gap-3"><Button type="submit" busy={busy}>Save preference</Button><Button variant="secondary" disabled={busy} onClick={onCancel}>Cancel</Button></div>
  </form>
}
