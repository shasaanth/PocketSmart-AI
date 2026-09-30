document.addEventListener("DOMContentLoaded", function () {

    const imageInputs =
        document.querySelectorAll(".image-input");


    imageInputs.forEach(function (input) {

        input.addEventListener(
            "change",
            function (event) {

                const file =
                    event.target.files[0];

                const preview =
                    document.getElementById("image-preview");


                if (!file || !preview) {
                    return;
                }


                if (file.size > 5 * 1024 * 1024) {

                    alert(
                        "Image must be smaller than 5 MB."
                    );

                    input.value = "";

                    preview.innerHTML = "";

                    return;
                }


                const reader =
                    new FileReader();


                reader.onload =
                    function (e) {

                        preview.innerHTML =
                            `
                            <p><strong>Image Preview:</strong></p>
                            <img
                                src="${e.target.result}"
                                alt="Preview"
                            >
                            `;
                    };


                reader.readAsDataURL(file);

            }
        );

    });


    const forms =
        document.querySelectorAll(
            "form.planner-form"
        );


    forms.forEach(function (form) {

        form.addEventListener(
            "submit",
            function () {

                const button =
                    form.querySelector(
                        "button[type='submit']"
                    );


                if (button) {

                    button.disabled = true;

                    button.innerText =
                        "🤖 Generating AI Recommendations...";

                }

            }
        );

    });

});