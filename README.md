# Enhancing Macie data discovery capabilities with Textract as an overlay

This solution uses Amazon Textract as an additional conversion layer to convert image data into a JSON format that is supported by Macie. This enhancement effectively expends the coverage capabilities of what Macie can offer.


AWS Services used
- Application Composer - to generate baseline template and resources
- Amazon Textract
- Amazon Macie
- AWS Lambda
- Amazon Simple notification service
- Amazon DynamoDB
- Amazon S3
- Amazon EventBridge

Solution Architecture
![solution-architecture](/static/images/architecture-diagram.png)

## Prerequisites
In your own AWS environment, make sure that you have the following set up:

* Enable Macie in your account. For instructions, see [Getting Started with Amazon Macie](https://docs.aws.amazon.com/macie/latest/user/getting-started.html)

* Access and permission to deploy the related AWS services in CloudFormation shown above.

* Determine the regular expression (regex) pattern for any sensitive textual data that you would like Macie to detect. This will allow you to create custom data identifiers that complement Macie's managed identifiers. For guidance, refer to [Building custom data identifiers in Amazon Macie](https://docs.aws.amazon.com/macie/latest/user/custom-data-identifiers.html). 

* [AWS SAM CLI installed](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html). We will deploy the solution using AWS SAM. If you would like to understand more about how AWS SAM works and its specification, you can refer to this [documentation](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/sam-specification.html) that explains more in detail.


## Deployment steps
### Deploying the SAM template with AWS SAM CLI
1. Make sure that you have AWS SAM CLI installed. Otherwise, please [follow the steps here to install](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html) the AWS SAM CLI.
2. Open a CLI window, navigate to your preferred local directory and run git clone https://github.com/aws-samples/enhancing-macie-with-textract
3. Navigate to this directory with cd enhancing-macie-with-textract.
4. Deploy the SAM template using `sam deploy --guided`. 
5. Follow the step-by-step instructions to indicate the deployment details such as the desired CloudFormation stack name, AWS Region, and other details 

Note: List of descriptions to some of the requested parameters
- ExistingS3BucketName — This is the S3 bucket name for the S3 you would like this solution to scan. This is an optional parameter, and if left blank, the solution will create a S3 bucket for you to store the objects you would like to scan
- MacieCustomCustomIdentifierIDList — This field allows you to enter a list of custom identifiers for Macie to detect with. If there is more than one ID, each ID should be separated by a comma. (e.g. 59fd2814-0ba8-41cc-adb2-1ffec6a0bb3c, 665cf948-ea30-42df-9f63-9a858cbfe1a8)
- EmailAddress — This is the email address that you would like to receive Amazon SNS email notification to, for Macie job completion.
- MacieLogGroupExists — This checks if you have an existing Macie CloudWatch Log Group ('/aws/macie/classificationjobs'). If it is your first time running a Macie job, enter `No` or `n`. Else, enter `Yes` or `y` .


6. Follow through the other deployment steps and deploy the changeset created.
7. After deployment is complete, you should see the following output: Successfully created/updated stack – {StackName} in {AWSRegion}. You can review the resources and stack in your CloudFormation console.
8. Check your email entered in step 5 to confirm the SNS subscription to receive notification when the Macie scan is done.

![sample-sam-deploy](/static/images/sample-sam-deploy.png)

### Testing out the Macie Enhanced scan
1. Navigate to the bucket you specified during deployment, in the AWS console. If you did not specify an S3 bucket to scan, a new bucket  `s3-with-sensitive-data-<account-id>-<random-string>` would have been created; navigate there
2. In your project directory, there are sample images in sample-images.zip. Unzip the file and upload the sample images into the S3 bucket. The sample images include a US driving license, social security card, passport, and a Singapore National Registration Identity Card (NRIC).
3. Navigate to the AWS Lambda console and select the lambda function `{StackName}-TextractTriggerLambda-<random-string>`
4. Start the automated sensitive data discovery process for the uploaded images by going to the “Test” tab and clicking “Test”.
5. The whole process will take about 15 minutes to complete. You will receive an email notification once the Macie scan is completed, as shown below.

![sample-macie-completed-sns](/static/images/sample-macie-completed-sns.png)

## Clean up the resources
To clean up the resources that you created for this example, follow the steps below:

1. To empty your S3 bucket, go to S3 and select for your bucket name starting with "s3-with-sensitive-data". Click “Empty" and follow the instruction on screen to empty it
2. Either (1) go to the CloudFormation console and delete the stack, or (2) run the following in your terminal to delete with AWS SAM CLI:
`sam delete`
3. Follow through the instruction on your terminal and select `y` when prompted for the decision to delete the stack.
