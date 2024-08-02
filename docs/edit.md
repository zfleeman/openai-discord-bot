```plaintext
!edit <prompt>
```

The `!edit` command edits an image using an original image and a mask. The user provides a prompt describing the desired edit. The edited image is generated using [OpenAI's image editing capabilities](https://platform.openai.com/docs/guides/images/edits-dall-e-2-only) and sent back to the user.

Attach the images to the same message your as your command. The original image must be attached first, with the image's mask attached second. Your prompt should describe the full new image, not just the erased area.