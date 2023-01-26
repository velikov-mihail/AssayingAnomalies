function X = csppstrtrem(Z,a,b)
% CSPPSTRTREM Projection pursuit structure removal.
%
%   X = CSPPSTRTREM(Z,ALPHA,BETA) Removes the structure
%   in a projection to the plane spanned by ALPHA and BETA.
%   Usually, this plane is found using projection pursuit EDA.
%   
%   The input matrix Z is an n x d matrix of spherized observations,
%   one for each row. The output matrix X is the data with the
%   structure removed.
%
%   See also CSPPEDA, CSPPIND

%   W. L. and A. R. Martinez, 9/15/01
%   Computational Statistics Toolbox 


% just do this 5 times
maxiter=5;	% maximum number of iterations allowed
[n,d]=size(Z);

% find the orthonormal matrix needed via Gram-Schmidt
U = eye(d,d);   
U(1,:)=a';	% vector for best plane
U(2,:)=b';
for i=3:d
   for j = 1:(i-1)
      U(i,:)=U(i,:)-(U(j,:)*U(i,:)')*U(j,:);
   end
   U(i,:)=U(i,:)/sqrt(sum(U(i,:).^2));
end

% Transform data using the matrix U
T = U*Z';	% to match Friedman's treatment. T is d x n
x1=T(1,:);	% These should be the 2-d projection that is 'best'
x2=T(2,:);

% Gaussianize the first two rows of T
% set of vector of angles
gam = [0,pi/4, pi/8, 3*pi/8];
for m = 1:maxiter
   % gaussianize the data
   for i=1:4
      % rotate about origin
      xp1 = x1*cos(gam(i))+x2*sin(gam(i));
      xp2 = x2*cos(gam(i))-x1*sin(gam(i));
      % Transform to normality
      [m,rnk1]=sort(xp1);  % get the ranks
      [m,rnk2]=sort(xp2);
      arg1 = (rnk1-0.5)/n;	% get the arguments
      arg2 = (rnk2-0.5)/n;
      x1 = norminv(arg1,0,1); % transform to normality
      x2 = norminv(arg2,0,1);
   end
end

% Set the first two rows of T to the Gaussianized values
T(1,:) = x1;
T(2,:) = x2;

X = (U'*T)';
