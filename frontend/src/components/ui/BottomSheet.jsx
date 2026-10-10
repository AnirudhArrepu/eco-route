import Modal from './Modal'

export default function BottomSheet(props) {
  return <Modal {...props} className={`bottom-sheet ${props.className || ''}`} />
}
