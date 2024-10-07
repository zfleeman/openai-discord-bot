```plaintext
!image <image_prompt> [image_model] [num_images]
```
The `!image` command generates an image using the specified prompt and model, then sends the generated image in the channel. 

`dall-e-2` prompts can generate multiple images if `num_images` is set to an integer > 1. Your OpenAI "organization" limits apply, here.

**The prompt must be surrounded in quotes.**
### Model Choices
- `dall-e-2`
- `dall-e-3` (default)
- `dall-e-3-hd`